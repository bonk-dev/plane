# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): estimates shown in published projects.

# Third Party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from .base import BaseAPIView
from plane.db.models import DeployBoard, EstimatePoint, Project


class ProjectEstimatePublicEndpoint(BaseAPIView):
    """Active estimate of a published project, so the public view can show issue estimates."""

    permission_classes = [AllowAny]

    def get(self, request, anchor):
        deploy_board = DeployBoard.objects.filter(anchor=anchor, entity_name="project").first()
        if not deploy_board:
            return Response({"error": "Project is not published"}, status=status.HTTP_404_NOT_FOUND)

        project = (
            Project.objects.filter(pk=deploy_board.entity_identifier, workspace_id=deploy_board.workspace_id)
            .select_related("estimate")
            .first()
        )
        if project is None or project.estimate is None:
            return Response({"type": None, "points": []}, status=status.HTTP_200_OK)

        points = EstimatePoint.objects.filter(estimate=project.estimate).order_by("key").values("id", "key", "value")
        return Response({"type": project.estimate.type, "points": list(points)}, status=status.HTTP_200_OK)
