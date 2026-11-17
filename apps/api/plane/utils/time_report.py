# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): project time report (estimate vs. logged time), shared by the
# project view and the published-project (space) view.

# Python imports
import csv
import io
from collections import defaultdict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Django imports
from django.db.models import Sum
from django.http import HttpResponse
from django.utils.http import content_disposition_header

# Third Party imports
from openpyxl import Workbook
from openpyxl.styles import Font

# Module imports
from plane.db.models import Issue, IssueAssignee, IssueWorkLog, StateGroup
from plane.utils.csv_utils import sanitize_csv_row

REPORT_GROUPS = ("issue", "member", "person")
UNASSIGNED_LABEL = "(nieprzypisane)"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def minutes_to_hours(minutes):
    return round((minutes or 0) / 60, 2)


def _estimate_minutes(point):
    """Minutes of a time estimate; None for no estimate or point/category estimates (not hours)."""
    if point is None or point.estimate.type != "time":
        return None
    try:
        return float(point.value)
    except ValueError:
        return None


def estimate_display(point):
    """Hours for time estimates (stored in minutes), otherwise the point/category value as-is."""
    if point is None:
        return None
    minutes = _estimate_minutes(point)
    if minutes is not None:
        return minutes_to_hours(minutes)
    return point.value


def _difference(logged_minutes, estimate_minutes):
    """logged - estimate in hours; empty when there is no time estimate to compare against."""
    if estimate_minutes is None:
        return None
    return round((logged_minutes - estimate_minutes) / 60, 2)


def project_tz(project):
    try:
        return ZoneInfo(project.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _local(value, tz):
    """Naive datetime in the project timezone (Excel cannot store timezone-aware datetimes)."""
    if value is None:
        return None
    return value.astimezone(tz).replace(tzinfo=None, microsecond=0)


def _issue_details(issue, tz):
    """State and planned vs. actual dates of a work item (None = empty cell)."""
    completed_at = _local(issue.completed_at, tz)
    delay_days = None
    if completed_at is not None and issue.target_date is not None:
        delay_days = (completed_at.date() - issue.target_date).days
    return {
        "state": issue.state.name if issue.state else None,
        "state_group": issue.state.group if issue.state else None,
        "created_at": _local(issue.created_at, tz),
        "start_date": issue.start_date,
        "target_date": issue.target_date,
        "completed_at": completed_at,
        "delay_days": delay_days,
    }


class _Summary:
    """Sum of estimates / logged time and work item counts per key (person, or the whole project)."""

    def __init__(self, label):
        self.label = label
        self.groups = {}

    def add(self, key, estimate_minutes, logged_minutes, closed):
        acc = self.groups.setdefault(
            key, {"estimate_minutes": None, "logged_minutes": 0, "issues": 0, "closed_issues": 0}
        )
        if estimate_minutes is not None:
            acc["estimate_minutes"] = (acc["estimate_minutes"] or 0) + estimate_minutes
        acc["logged_minutes"] += logged_minutes
        acc["issues"] += 1
        acc["closed_issues"] += int(closed)

    def rows(self):
        # "(nieprzypisane)" goes last
        keys = sorted(self.groups, key=lambda k: (k == UNASSIGNED_LABEL, k.lower()))
        return [
            {
                self.label: key,
                "estimate_h": (
                    minutes_to_hours(self.groups[key]["estimate_minutes"])
                    if self.groups[key]["estimate_minutes"] is not None
                    else None
                ),
                "logged_h": minutes_to_hours(self.groups[key]["logged_minutes"]),
                "issues": self.groups[key]["issues"],
                "closed_issues": self.groups[key]["closed_issues"],
            }
            for key in keys
        ]


def build_time_report(project):
    """Every view of the project time report: per work item, per person, per person × work item,
    every time entry, and the summary per person and for the whole project."""
    tz = project_tz(project)
    worklogs = (
        IssueWorkLog.objects.filter(workspace_id=project.workspace_id, project_id=project.id)
        .select_related("issue", "created_by")
        .order_by("logged_date", "created_at")
    )
    # Archived work items stay in the report (completed ones are often auto-archived); drafts and triage do not
    issues = list(
        Issue.objects.filter(workspace_id=project.workspace_id, project_id=project.id, is_draft=False)
        .exclude(state__group=StateGroup.TRIAGE.value)
        .select_related("state", "estimate_point", "estimate_point__estimate")
        .order_by("sequence_id")
    )

    def identifier(issue):
        return f"{project.identifier}-{issue.sequence_id}"

    # Per work item: every issue that has an estimate or logged time
    logged_by_issue = {
        row["issue_id"]: row["total"] for row in worklogs.values("issue_id").annotate(total=Sum("duration")).order_by()
    }
    details = {}
    issue_rows = []
    reported_issues = []
    for issue in issues:
        estimate = issue.estimate_point
        logged = logged_by_issue.get(issue.id, 0)
        if estimate is None and not logged:
            continue
        details[issue.id] = _issue_details(issue, tz)
        reported_issues.append(issue)
        issue_rows.append(
            {
                "issue_id": str(issue.id),
                "identifier": identifier(issue),
                "name": issue.name,
                "estimate_value": estimate.value if estimate else None,
                "estimate_type": estimate.estimate.type if estimate else None,
                "logged_minutes": logged,
                "logged_hours": minutes_to_hours(logged),
                "difference_h": _difference(logged, _estimate_minutes(estimate)),
                **details[issue.id],
            }
        )

    # Per person
    member_rows = [
        {
            "user_id": str(row["created_by_id"]),
            "display_name": row["created_by__display_name"],
            "logged_minutes": row["total"],
            "logged_hours": minutes_to_hours(row["total"]),
        }
        for row in worklogs.values("created_by_id", "created_by__display_name")
        .annotate(total=Sum("duration"))
        .order_by("-total")
    ]

    # Per person and work item: the work item's estimate against the time that person logged on it.
    # Estimated work items nobody logged time on yet are listed under their assignees.
    issues_by_id = {issue.id: issue for issue in reported_issues}
    person_minutes = defaultdict(int)
    person_keys = set()
    for w in worklogs:
        key = (w.created_by.display_name if w.created_by else "", w.issue_id)
        person_minutes[key] += w.duration
        # time logged on draft/deleted work items is still listed in the entries, not here
        if w.issue_id in issues_by_id:
            person_keys.add(key)
    estimated_without_logs = [
        issue.id for issue in reported_issues if issue.estimate_point_id and issue.id not in logged_by_issue
    ]
    assigned = defaultdict(list)
    for row in IssueAssignee.objects.filter(issue_id__in=estimated_without_logs).values(
        "issue_id", "assignee__display_name"
    ):
        assigned[row["issue_id"]].append(row["assignee__display_name"])
    for issue_id in estimated_without_logs:
        for display_name in assigned.get(issue_id) or [""]:
            person_keys.add((display_name, issue_id))

    person_summary = _Summary("display_name")
    person_rows = []
    for display_name, issue_id in sorted(
        person_keys, key=lambda key: (key[0].lower(), issues_by_id[key[1]].sequence_id)
    ):
        issue = issues_by_id[issue_id]
        estimate_minutes = _estimate_minutes(issue.estimate_point)
        logged = person_minutes[(display_name, issue_id)]
        person_rows.append(
            {
                "display_name": display_name,
                "identifier": identifier(issue),
                "name": issue.name,
                "estimate": estimate_display(issue.estimate_point),
                "logged_hours": minutes_to_hours(logged),
                "difference_h": _difference(logged, estimate_minutes),
                # all people together; differs from logged_hours when several people worked on it
                "issue_logged_hours": minutes_to_hours(logged_by_issue.get(issue_id, 0)),
                **details[issue_id],
            }
        )
        person_summary.add(
            display_name or UNASSIGNED_LABEL,
            estimate_minutes,
            logged,
            details[issue_id]["state_group"] == StateGroup.COMPLETED.value,
        )

    # Whole project: each work item once, however many people worked on it
    total_summary = _Summary("name")
    for issue in reported_issues:
        total_summary.add(
            "total",
            _estimate_minutes(issue.estimate_point),
            logged_by_issue.get(issue.id, 0),
            details[issue.id]["state_group"] == StateGroup.COMPLETED.value,
        )
    [total_row] = total_summary.rows() or [
        {"name": "total", "estimate_h": None, "logged_h": 0.0, "issues": 0, "closed_issues": 0}
    ]

    entry_rows = [
        {
            "id": str(w.id),
            "logged_date": w.logged_date,
            "identifier": identifier(w.issue),
            "issue_name": w.issue.name,
            "display_name": w.created_by.display_name if w.created_by else "",
            "duration_minutes": w.duration,
            "duration_hours": minutes_to_hours(w.duration),
            "description": w.description,
        }
        for w in worklogs
    ]

    total = sum(row["logged_minutes"] for row in member_rows)
    return {
        "total_minutes": total,
        "total_hours": minutes_to_hours(total),
        "issues": issue_rows,
        "members": member_rows,
        "people": person_rows,
        "entries": entry_rows,
        "summary": {
            "people": person_summary.rows(),
            "total": total_row,
        },
    }


def _append_table(sheet, rows, bold):
    if not rows:
        return
    sheet.append(list(rows[0].keys()))
    for cell in sheet[sheet.max_row]:
        cell.font = bold
    for row in rows:
        sheet.append(sanitize_csv_row(row.values()))


def _fit_columns(sheet):
    widths = defaultdict(int)
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None:
                widths[cell.column_letter] = max(widths[cell.column_letter], len(str(cell.value)))
    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = min(max(width + 2, 10), 60)


EXPORT_FORMATS = ("csv", "xlsx", "pdf")


def time_report_export(project, export, group=None):
    """CSV or XLSX file of one report view (XLSX also gets a "Podsumowanie" sheet),
    or the PDF report (work items per person + summaries with charts; group is ignored)."""
    report = build_time_report(project)
    if export == "pdf":
        from plane.utils.time_report_pdf import time_report_pdf

        response = HttpResponse(time_report_pdf(project, report, project_tz(project)), content_type="application/pdf")
        response["Content-Disposition"] = content_disposition_header(True, f"{project.identifier}-raport-czasu.pdf")
        return response
    rows = {"issue": report["issues"], "member": report["members"], "person": report["people"]}.get(
        group, report["entries"]
    )
    filename = f"{project.identifier}-worklogs{'-' + group if group in REPORT_GROUPS else ''}"

    if export == "xlsx":
        bold = Font(bold=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Worklogs"
        _append_table(sheet, rows, bold)
        sheet.freeze_panes = "A2"
        _fit_columns(sheet)

        summary = workbook.create_sheet("Podsumowanie")
        summary.append(["Per osoba"])
        summary.cell(row=1, column=1).font = Font(bold=True, size=12)
        _append_table(summary, report["summary"]["people"], bold)
        _fit_columns(summary)

        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    else:
        buffer = io.StringIO()
        # BOM so that Excel opens Polish characters correctly
        buffer.write("﻿")
        if rows:
            writer = csv.writer(buffer, delimiter=";")
            writer.writerow(list(rows[0].keys()))
            writer.writerows(sanitize_csv_row(row.values()) for row in rows)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    # filename*= keeps non-ASCII project identifiers (e.g. "INŻYN") intact
    response["Content-Disposition"] = content_disposition_header(True, f"{filename}.{export}")
    return response
