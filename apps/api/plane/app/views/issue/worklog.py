# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items.

# Third Party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from .. import BaseAPIView, BaseViewSet
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueWorkLogSerializer
from plane.db.models import Issue, IssueWorkLog, Project
from plane.utils.time_report import EXPORT_FORMATS, build_time_report, time_report_export


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


class ProjectWorkLogEndpoint(BaseAPIView):
    """Project-wide time report: estimate vs. logged time per work item and per person.

    GET ...?export=csv              -> every time entry as CSV (export=xlsx for an Excel file)
    GET ...?export=csv&group=issue  -> one row per work item (estimate vs. logged)
    GET ...?export=csv&group=member -> one row per person
    GET ...?export=csv&group=person -> one row per person and work item (estimate vs. their logged time)

    XLSX files get a second "Podsumowanie" sheet (per person / module / cycle).
    GET ...?export=pdf              -> PDF report: work items, summaries and estimate vs. logged charts
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if project is None:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        export = request.GET.get("export")
        if export in EXPORT_FORMATS:
            return time_report_export(project, export, request.GET.get("group"))
        return Response(build_time_report(project), status=status.HTTP_200_OK)
