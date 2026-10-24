/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): time logged on work items.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";

export type TIssueWorkLog = {
  id: string;
  issue: string;
  project: string;
  workspace: string;
  /** minutes */
  duration: number;
  /** YYYY-MM-DD */
  logged_date: string;
  description: string;
  created_by: string;
  created_by_detail?: {
    id: string;
    display_name: string;
    avatar_url?: string;
  };
  created_at: string;
  updated_at: string;
};

export type TIssueWorkLogPayload = Pick<TIssueWorkLog, "duration" | "logged_date" | "description">;

export class IssueWorkLogService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private base(workspaceSlug: string, projectId: string, issueId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/worklogs/`;
  }

  async list(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueWorkLog[]> {
    return this.get(this.base(workspaceSlug, projectId, issueId))
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async create(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    payload: TIssueWorkLogPayload
  ): Promise<TIssueWorkLog> {
    return this.post(this.base(workspaceSlug, projectId, issueId), payload)
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async remove(workspaceSlug: string, projectId: string, issueId: string, workLogId: string): Promise<void> {
    return this.delete(`${this.base(workspaceSlug, projectId, issueId)}${workLogId}/`)
      .then(() => undefined)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  /** Direct link to the project-wide CSV report (uses the browser session cookie). */
  static reportCsvUrl(workspaceSlug: string, projectId: string, group?: "issue" | "member") {
    const params = new URLSearchParams({ export: "csv" });
    if (group) params.set("group", group);
    return `${API_BASE_URL}/api/workspaces/${workspaceSlug}/projects/${projectId}/worklogs/?${params.toString()}`;
  }
}
