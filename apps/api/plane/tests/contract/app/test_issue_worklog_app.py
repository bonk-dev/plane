# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
#
# Custom addition (fork): time logged on work items.

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    DeployBoard,
    Estimate,
    EstimatePoint,
    Issue,
    IssueWorkLog,
    Project,
    ProjectMember,
    User,
    Workspace,
    WorkspaceMember,
)


def _user(prefix):
    uid = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{uid}@plane.so", username=f"{prefix}_{uid}", display_name=prefix, first_name=prefix
    )
    user.set_password("test-password")
    user.save()
    return user


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def setup(db):
    admin = _user("admin")
    member = _user("member")
    guest = _user("guest")
    outsider = _user("outsider")
    ws = Workspace.objects.create(name="WS", owner=admin, slug=f"ws-{uuid4().hex[:8]}")
    for user, role in ((admin, 20), (member, 15), (guest, 5), (outsider, 15)):
        WorkspaceMember.objects.create(workspace=ws, member=user, role=role)
    project = Project.objects.create(name="Proj", identifier="PRJ", workspace=ws, created_by=admin)
    for user, role in ((admin, 20), (member, 15), (guest, 5)):
        ProjectMember.objects.create(project=project, member=user, workspace=ws, role=role)
    other_project = Project.objects.create(name="Other", identifier="OTH", workspace=ws, created_by=outsider)
    ProjectMember.objects.create(project=other_project, member=outsider, workspace=ws, role=20)

    estimate = Estimate.objects.create(name="Godziny", type="time", project=project)
    point = EstimatePoint.objects.create(estimate=estimate, key=1, value="120", project=project)
    issue = Issue.objects.create(name="Formularz logowania", project=project, workspace=ws, estimate_point=point)
    other_issue = Issue.objects.create(name="Obce", project=other_project, workspace=ws)
    return {
        "admin": admin,
        "member": member,
        "guest": guest,
        "outsider": outsider,
        "ws": ws,
        "project": project,
        "issue": issue,
        "other_project": other_project,
        "other_issue": other_issue,
    }


def issue_url(s, issue=None, project=None):
    project = project or s["project"]
    issue = issue or s["issue"]
    return f"/api/workspaces/{s['ws'].slug}/projects/{project.id}/issues/{issue.id}/worklogs/"


def report_url(s):
    return f"/api/workspaces/{s['ws'].slug}/projects/{s['project'].id}/worklogs/"


@pytest.mark.contract
class TestIssueWorkLog:
    def test_member_logs_time_and_lists_it(self, setup):
        client = _client(setup["member"])
        resp = client.post(
            issue_url(setup),
            {"duration": 90, "logged_date": "2026-10-20", "description": "walidacja"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        assert resp.data["duration"] == 90
        assert resp.data["created_by"] == setup["member"].id
        assert resp.data["created_by_detail"]["display_name"] == "member"

        resp = client.get(issue_url(setup))
        assert resp.status_code == status.HTTP_200_OK
        assert [w["duration"] for w in resp.data] == [90]

    def test_server_controls_issue_and_author(self, setup):
        client = _client(setup["member"])
        resp = client.post(
            issue_url(setup),
            {"duration": 30, "issue": str(setup["other_issue"].id), "created_by": str(setup["admin"].id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        log = IssueWorkLog.objects.get(pk=resp.data["id"])
        assert log.issue_id == setup["issue"].id
        assert log.created_by_id == setup["member"].id

    @pytest.mark.parametrize("duration", [0, -5, 24 * 60 + 1, "abc"])
    def test_invalid_duration_rejected(self, setup, duration):
        resp = _client(setup["member"]).post(issue_url(setup), {"duration": duration}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_can_read_but_not_log(self, setup):
        client = _client(setup["guest"])
        assert client.get(issue_url(setup)).status_code == status.HTTP_200_OK
        resp = client.post(issue_url(setup), {"duration": 10}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_outsider_cannot_read_or_log(self, setup):
        client = _client(setup["outsider"])
        assert client.get(issue_url(setup)).status_code == status.HTTP_403_FORBIDDEN
        assert client.post(issue_url(setup), {"duration": 10}, format="json").status_code == 403

    def test_issue_from_other_project_is_404(self, setup):
        # Member of PRJ, but the issue belongs to OTH
        resp = _client(setup["member"]).post(
            issue_url(setup, issue=setup["other_issue"]), {"duration": 10}, format="json"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_only_author_or_admin_can_edit_and_delete(self, setup):
        log = _client(setup["admin"]).post(issue_url(setup), {"duration": 60}, format="json").data
        url = issue_url(setup) + f"{log['id']}/"

        member = _client(setup["member"])
        assert member.patch(url, {"duration": 5}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert member.delete(url).status_code == status.HTTP_403_FORBIDDEN

        own = member.post(issue_url(setup), {"duration": 15}, format="json").data
        own_url = issue_url(setup) + f"{own['id']}/"
        resp = member.patch(own_url, {"duration": 20, "description": "poprawka"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["duration"] == 20

        # admin can delete someone else's entry
        assert _client(setup["admin"]).delete(own_url).status_code == status.HTTP_204_NO_CONTENT
        assert member.delete(url).status_code == status.HTTP_403_FORBIDDEN
        assert _client(setup["admin"]).delete(url).status_code == status.HTTP_204_NO_CONTENT
        assert IssueWorkLog.objects.filter(issue=setup["issue"]).count() == 0

    def test_project_report_and_csv(self, setup):
        _client(setup["member"]).post(issue_url(setup), {"duration": 90, "description": "a"}, format="json")
        _client(setup["admin"]).post(issue_url(setup), {"duration": 60, "description": "b"}, format="json")

        resp = _client(setup["guest"]).get(report_url(setup))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_minutes"] == 150
        [issue_row] = resp.data["issues"]
        assert issue_row["identifier"] == f"PRJ-{setup['issue'].sequence_id}"
        assert issue_row["estimate_value"] == "120"
        assert issue_row["estimate_type"] == "time"
        assert issue_row["logged_minutes"] == 150
        assert {m["display_name"]: m["logged_minutes"] for m in resp.data["members"]} == {
            "member": 90,
            "admin": 60,
        }
        assert len(resp.data["entries"]) == 2

        csv_resp = _client(setup["member"]).get(report_url(setup) + "?export=csv&group=issue")
        assert csv_resp.status_code == status.HTTP_200_OK
        assert csv_resp["Content-Type"].startswith("text/csv")
        body = csv_resp.content.decode("utf-8-sig")
        assert body.splitlines()[0].startswith("issue_id;identifier;name;estimate_value")
        assert "Formularz logowania" in body

        assert _client(setup["outsider"]).get(report_url(setup)).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
class TestIssueWorkLogPublic:
    """Published project (Plane „Publish”): time entries are readable without login."""

    def _publish(self, s):
        return DeployBoard.objects.create(
            entity_name="project", entity_identifier=s["project"].id, project=s["project"], workspace=s["ws"]
        )

    def _url(self, anchor, issue):
        return f"/api/public/anchor/{anchor}/issues/{issue.id}/worklogs/"

    def test_anonymous_reads_entries_of_published_project(self, setup):
        board = self._publish(setup)
        _client(setup["member"]).post(issue_url(setup), {"duration": 90, "description": "a"}, format="json")

        resp = APIClient().get(self._url(board.anchor, setup["issue"]))
        assert resp.status_code == status.HTTP_200_OK
        [entry] = resp.data
        assert entry["duration"] == 90
        assert entry["display_name"] == "member"
        assert entry["description"] == "a"
        # no emails or user ids in the public response
        assert set(entry) == {"id", "duration", "logged_date", "description", "display_name"}

    def test_issue_outside_published_project_is_404(self, setup):
        board = self._publish(setup)
        resp = APIClient().get(self._url(board.anchor, setup["other_issue"]))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_unpublished_project_is_404(self, setup):
        resp = APIClient().get(self._url("not-a-real-anchor", setup["issue"]))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_public_endpoint_is_read_only(self, setup):
        board = self._publish(setup)
        resp = _client(setup["member"]).post(self._url(board.anchor, setup["issue"]), {"duration": 10}, format="json")
        assert resp.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.contract
class TestTimeEstimates:
    """Custom addition (fork): time estimates enabled in Community; shown in published projects."""

    def test_admin_creates_time_estimate(self, setup):
        url = f"/api/workspaces/{setup['ws'].slug}/projects/{setup['project'].id}/estimates/"
        resp = _client(setup["admin"]).post(
            url,
            {
                "estimate": {"name": "Czas", "type": "time"},
                "estimate_points": [{"key": 1, "value": "60"}, {"key": 2, "value": "90"}],
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["type"] == "time"
        assert sorted(p["value"] for p in resp.data["points"]) == ["60", "90"]

    def test_public_estimate_of_published_project(self, setup):
        project = setup["project"]
        project.estimate = setup["issue"].estimate_point.estimate
        project.save()
        board = DeployBoard.objects.create(
            entity_name="project", entity_identifier=project.id, project=project, workspace=setup["ws"]
        )

        resp = APIClient().get(f"/api/public/anchor/{board.anchor}/estimates/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["type"] == "time"
        assert resp.data["points"] == [{"id": setup["issue"].estimate_point.id, "key": 1, "value": "120"}]

    def test_public_estimate_without_active_estimate(self, setup):
        board = DeployBoard.objects.create(
            entity_name="project",
            entity_identifier=setup["project"].id,
            project=setup["project"],
            workspace=setup["ws"],
        )
        resp = APIClient().get(f"/api/public/anchor/{board.anchor}/estimates/")
        assert resp.data == {"type": None, "points": []}

    def test_public_estimate_unpublished_is_404(self, setup):
        assert APIClient().get("/api/public/anchor/not-a-real-anchor/estimates/").status_code == 404
