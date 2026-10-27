# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items.

# Python imports
import csv
import io
from collections import defaultdict

# Django imports
from django.db.models import Sum
from django.http import HttpResponse
from django.utils.http import content_disposition_header

# Third Party imports
from openpyxl import Workbook
from rest_framework import status
from rest_framework.response import Response

# Module imports
from .. import BaseAPIView, BaseViewSet
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueWorkLogSerializer
from plane.db.models import Issue, IssueAssignee, IssueWorkLog, Project
from plane.utils.csv_utils import sanitize_csv_row


def issue_in_project(issue_id, slug, project_id):
    """The URL issue must belong to the URL workspace + project (archived included)."""
    return Issue.objects.filter(pk=issue_id, workspace__slug=slug, project_id=project_id).exists()


WORKLOG_WRITABLE_FIELDS = ("duration", "logged_date", "description")


class IssueWorkLogViewSet(BaseViewSet):
    """CRUD for time entries of a single work item.

    Any project member (admin/member) can log time; only the author or a project
    admin can edit or delete an entry.
    """

    serializer_class = IssueWorkLogSerializer
    model = IssueWorkLog

    def get_queryset(self):
        return (
            IssueWorkLog.objects.filter(
                workspace__slug=self.kwargs.get("slug"),
                project_id=self.kwargs.get("project_id"),
                issue_id=self.kwargs.get("issue_id"),
                issue__project_id=self.kwargs.get("project_id"),
                project__archived_at__isnull=True,
            )
            .select_related("created_by")
            .order_by("-logged_date", "-created_at")
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def list(self, request, slug, project_id, issue_id):
        if not issue_in_project(issue_id, slug, project_id):
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = IssueWorkLogSerializer(self.get_queryset(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def create(self, request, slug, project_id, issue_id):
        if not issue_in_project(issue_id, slug, project_id):
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)
        data = {key: request.data[key] for key in WORKLOG_WRITABLE_FIELDS if key in request.data}
        serializer = IssueWorkLogSerializer(data=data)
        if serializer.is_valid():
            serializer.save(project_id=project_id, issue_id=issue_id)
            worklog = self.get_queryset().get(pk=serializer.data["id"])
            return Response(IssueWorkLogSerializer(worklog).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(allowed_roles=[ROLE.ADMIN], creator=True, model=IssueWorkLog)
    def partial_update(self, request, slug, project_id, issue_id, pk):
        worklog = self.get_queryset().filter(pk=pk).first()
        if worklog is None:
            return Response({"error": "Work log not found"}, status=status.HTTP_404_NOT_FOUND)
        data = {key: request.data[key] for key in WORKLOG_WRITABLE_FIELDS if key in request.data}
        serializer = IssueWorkLogSerializer(worklog, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @allow_permission(allowed_roles=[ROLE.ADMIN], creator=True, model=IssueWorkLog)
    def destroy(self, request, slug, project_id, issue_id, pk):
        worklog = self.get_queryset().filter(pk=pk).first()
        if worklog is None:
            return Response({"error": "Work log not found"}, status=status.HTTP_404_NOT_FOUND)
        worklog.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _minutes_to_hours(minutes):
    return round((minutes or 0) / 60, 2)


def _estimate(point):
    """Hours for time estimates (stored in minutes), otherwise the point/category value as-is."""
    if point is None:
        return None
    if point.estimate.type == "time":
        try:
            return _minutes_to_hours(float(point.value))
        except ValueError:
            return point.value
    return point.value


class ProjectWorkLogEndpoint(BaseAPIView):
    """Project-wide time report: estimate vs. logged time per work item and per person.

    GET ...?export=csv              -> every time entry as CSV (export=xlsx for an Excel file)
    GET ...?export=csv&group=issue  -> one row per work item (estimate vs. logged)
    GET ...?export=csv&group=member -> one row per person
    GET ...?export=csv&group=person -> one row per person and work item (estimate vs. their logged time)
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if project is None:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        worklogs = (
            IssueWorkLog.objects.filter(workspace__slug=slug, project_id=project_id)
            .select_related("issue", "issue__estimate_point__estimate", "created_by")
            .order_by("logged_date", "created_at")
        )

        # Per work item: every issue that has an estimate or logged time
        logged_by_issue = {
            row["issue_id"]: row["total"]
            for row in worklogs.values("issue_id").annotate(total=Sum("duration")).order_by()
        }
        issues = (
            Issue.issue_objects.filter(workspace__slug=slug, project_id=project_id)
            .select_related("estimate_point", "estimate_point__estimate")
            .order_by("sequence_id")
        )
        issue_rows = []
        for issue in issues:
            estimate = issue.estimate_point
            logged = logged_by_issue.get(issue.id, 0)
            if estimate is None and not logged:
                continue
            issue_rows.append(
                {
                    "issue_id": str(issue.id),
                    "identifier": f"{project.identifier}-{issue.sequence_id}",
                    "name": issue.name,
                    "estimate_value": estimate.value if estimate else None,
                    "estimate_type": estimate.estimate.type if estimate else None,
                    "logged_minutes": logged,
                    "logged_hours": _minutes_to_hours(logged),
                }
            )

        # Per person
        member_rows = [
            {
                "user_id": str(row["created_by_id"]),
                "display_name": row["created_by__display_name"],
                "logged_minutes": row["total"],
                "logged_hours": _minutes_to_hours(row["total"]),
            }
            for row in worklogs.values("created_by_id", "created_by__display_name")
            .annotate(total=Sum("duration"))
            .order_by("-total")
        ]

        # Per person and work item: the work item's estimate against the time that person logged on it.
        # Estimated work items nobody logged time on yet are listed under their assignees.
        person_minutes = defaultdict(int)
        person_issues = {}
        for w in worklogs:
            key = (w.created_by.display_name if w.created_by else "", w.issue_id)
            person_minutes[key] += w.duration
            person_issues[key] = w.issue
        estimated_without_logs = {
            issue.id: issue for issue in issues if issue.estimate_point_id and issue.id not in logged_by_issue
        }
        assigned = defaultdict(list)
        for row in IssueAssignee.objects.filter(issue_id__in=list(estimated_without_logs)).values(
            "issue_id", "assignee__display_name"
        ):
            assigned[row["issue_id"]].append(row["assignee__display_name"])
        for issue_id, issue in estimated_without_logs.items():
            for display_name in assigned.get(issue_id) or [""]:
                person_issues[(display_name, issue_id)] = issue
        person_rows = [
            {
                "display_name": display_name,
                "identifier": f"{project.identifier}-{issue.sequence_id}",
                "name": issue.name,
                "estimate": _estimate(issue.estimate_point),
                "logged_hours": _minutes_to_hours(person_minutes[(display_name, issue_id)]),
            }
            for (display_name, issue_id), issue in sorted(
                person_issues.items(), key=lambda item: (item[0][0].lower(), item[1].sequence_id)
            )
        ]

        entry_rows = [
            {
                "id": str(w.id),
                "logged_date": w.logged_date.isoformat(),
                "identifier": f"{project.identifier}-{w.issue.sequence_id}",
                "issue_name": w.issue.name,
                "display_name": w.created_by.display_name if w.created_by else "",
                "duration_minutes": w.duration,
                "duration_hours": _minutes_to_hours(w.duration),
                "description": w.description,
            }
            for w in worklogs
        ]

        export = request.GET.get("export")
        if export in ("csv", "xlsx"):
            group = request.GET.get("group")
            rows = {"issue": issue_rows, "member": member_rows, "person": person_rows}.get(group, entry_rows)
            filename = f"{project.identifier}-worklogs{'-' + group if group in ('issue', 'member', 'person') else ''}"
            fieldnames = list(rows[0].keys()) if rows else []
            if export == "xlsx":
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = "Worklogs"
                sheet.append(fieldnames)
                for row in rows:
                    sheet.append(sanitize_csv_row(row.values()))
                buffer = io.BytesIO()
                workbook.save(buffer)
                response = HttpResponse(
                    buffer.getvalue(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                buffer = io.StringIO()
                # BOM so that Excel opens Polish characters correctly
                buffer.write("\ufeff")
                if rows:
                    writer = csv.writer(buffer, delimiter=";")
                    writer.writerow(fieldnames)
                    writer.writerows(sanitize_csv_row(row.values()) for row in rows)
                response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
            # filename*= keeps non-ASCII project identifiers (e.g. "INŻYN") intact
            response["Content-Disposition"] = content_disposition_header(True, f"{filename}.{export}")
            return response

        total = sum(row["logged_minutes"] for row in member_rows)
        return Response(
            {
                "total_minutes": total,
                "total_hours": _minutes_to_hours(total),
                "issues": issue_rows,
                "members": member_rows,
                "people": person_rows,
                "entries": entry_rows,
            },
            status=status.HTTP_200_OK,
        )
