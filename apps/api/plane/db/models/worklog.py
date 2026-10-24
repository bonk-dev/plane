# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items.

# Django imports
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# Module imports
from .project import ProjectBaseModel


def default_logged_date():
    return timezone.now().date()


class IssueWorkLog(ProjectBaseModel):
    """One time entry: who (created_by) spent how many minutes on which work item, on which day."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="issue_worklogs")
    # Stored in minutes to avoid floating point issues; max 24h per entry
    duration = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(24 * 60)])
    logged_date = models.DateField(default=default_logged_date)
    description = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Issue Work Log"
        verbose_name_plural = "Issue Work Logs"
        db_table = "issue_worklogs"
        ordering = ("-logged_date", "-created_at")

    def __str__(self):
        return f"{self.issue_id} {self.duration}min"
