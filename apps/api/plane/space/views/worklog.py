# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items, read-only in published projects.

# Third Party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from .base import BaseAPIView
from plane.db.models import DeployBoard, Issue, IssueWorkLog, Project
from plane.utils.time_report import EXPORT_FORMATS, time_report_export


class IssueWorkLogPublicEndpoint(BaseAPIView):
    """Time entries of a work item in a published project. Visible to anyone with the link."""

    permission_classes = [AllowAny]

    def get(self, request, anchor, issue_id):
        deploy_board = DeployBoard.objects.filter(anchor=anchor, entity_name="project").first()
        if not deploy_board:
            return Response({"error": "Project is not published"}, status=status.HTTP_404_NOT_FOUND)

        project_id = deploy_board.entity_identifier
        if not Issue.issue_objects.filter(
            pk=issue_id, workspace_id=deploy_board.workspace_id, project_id=project_id
        ).exists():
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        # Only what the published view shows; no emails or user ids
        worklogs = (
            IssueWorkLog.objects.filter(issue_id=issue_id, project_id=project_id)
            .order_by("-logged_date", "-created_at")
            .values("id", "duration", "logged_date", "description", "created_by__display_name")
        )
        return Response(
            [
                {
                    "id": w["id"],
                    "duration": w["duration"],
                    "logged_date": w["logged_date"],
                    "description": w["description"],
                    "display_name": w["created_by__display_name"] or "",
                }
                for w in worklogs
            ],
            status=status.HTTP_200_OK,
        )


class ProjectWorkLogReportPublicEndpoint(BaseAPIView):
    """Time report file of a published project (same as the project view, no user ids or entries).

    GET ...?export=xlsx&group=person (default) | group=issue, export=csv for a CSV file, export=pdf for the PDF report
    """

    permission_classes = [AllowAny]
    PUBLIC_GROUPS = ("person", "issue")

    def get(self, request, anchor):
        deploy_board = DeployBoard.objects.filter(anchor=anchor, entity_name="project").first()
        if not deploy_board:
            return Response({"error": "Project is not published"}, status=status.HTTP_404_NOT_FOUND)
        project = Project.objects.filter(
            pk=deploy_board.entity_identifier, workspace_id=deploy_board.workspace_id
        ).first()
        if project is None:
            return Response({"error": "Project is not published"}, status=status.HTTP_404_NOT_FOUND)

        export = request.GET.get("export", "xlsx")
        if export not in EXPORT_FORMATS:
            return Response({"error": "export must be csv, xlsx or pdf"}, status=status.HTTP_400_BAD_REQUEST)
        group = request.GET.get("group")
        if group not in self.PUBLIC_GROUPS:
            group = "person"
        return time_report_export(project, export, group)
