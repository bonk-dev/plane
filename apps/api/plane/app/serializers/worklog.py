# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items.

# Module imports
from .base import BaseSerializer
from .user import UserLiteSerializer
from plane.db.models import IssueWorkLog


class IssueWorkLogSerializer(BaseSerializer):
    created_by_detail = UserLiteSerializer(read_only=True, source="created_by")

    class Meta:
        model = IssueWorkLog
        fields = [
            "id",
            "issue",
            "project",
            "workspace",
            "duration",
            "logged_date",
            "description",
            "created_by",
            "created_by_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "issue",
            "project",
            "workspace",
            "created_by",
            "created_at",
            "updated_at",
        ]
