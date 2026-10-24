/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): time logged on work items, read-only in published projects.
 * Strings are intentionally hardcoded in Polish (not wired into @plane/i18n).
 */

import useSWR from "swr";
import { Timer } from "lucide-react";
// plane imports
import { SitesIssueService } from "@plane/services";

const issueService = new SitesIssueService();

/** 150 -> "2h 30m", 45 -> "45m", 120 -> "2h" (same as apps/web worklog/helpers.ts) */
const formatDuration = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
};

type Props = {
  anchor: string;
  issueId: string;
};

export function PeekOverviewIssueWorkLog({ anchor, issueId }: Props) {
  const { data: workLogs } = useSWR(
    anchor && issueId ? `PUBLIC_ISSUE_WORKLOGS_${anchor}_${issueId}` : null,
    () => issueService.listWorkLogs(anchor, issueId),
    { revalidateOnFocus: false }
  );
  const totalMinutes = (workLogs ?? []).reduce((sum, log) => sum + log.duration, 0);

  return (
    <div>
      <div className="flex h-8 items-center gap-3">
        <div className="flex w-1/4 flex-shrink-0 items-center gap-1 text-13 text-tertiary">
          <Timer className="size-4 flex-shrink-0" />
          <span>Spędzony czas</span>
        </div>
        <div className="w-3/4 text-13">
          {workLogs === undefined ? (
            "…"
          ) : totalMinutes > 0 ? (
            formatDuration(totalMinutes)
          ) : (
            <span className="text-secondary">Empty</span>
          )}
        </div>
      </div>
      {workLogs && workLogs.length > 0 && (
        <ul className="mt-1 divide-y divide-subtle-1 text-12">
          {workLogs.map((log) => (
            <li key={log.id} className="flex items-start gap-3 py-1.5">
              <span className="w-14 shrink-0 font-medium">{formatDuration(log.duration)}</span>
              <div className="min-w-0 grow">
                {log.description && <div className="break-words">{log.description}</div>}
                <div className="text-tertiary">
                  {log.display_name || "?"} · {log.logged_date}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
