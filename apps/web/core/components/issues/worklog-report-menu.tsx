/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): download the project time report (estimate vs. logged time).
 */

import { Timer } from "lucide-react";
// plane imports
import { getButtonStyling } from "@plane/propel/button";
import { CustomMenu } from "@plane/ui";
// services
import type { TWorkLogReportGroup } from "@/services/issue/issue_worklog.service";
import { IssueWorkLogService } from "@/services/issue/issue_worklog.service";

const REPORTS: { group?: TWorkLogReportGroup; label: string }[] = [
  { group: "person", label: "Osoba – zadanie – estymata – czas" },
  { group: "issue", label: "Zadania: estymata vs. czas" },
  { group: "member", label: "Suma czasu per osoba" },
  { label: "Wszystkie wpisy czasu" },
];

type Props = {
  workspaceSlug: string;
  projectId: string;
};

export function WorkLogReportMenu(props: Props) {
  const { workspaceSlug, projectId } = props;

  return (
    <CustomMenu
      customButton={
        <span className={getButtonStyling("secondary", "lg")}>
          <Timer className="size-3" />
          <span className="shrink-0">Raport czasu</span>
        </span>
      }
      placement="bottom-end"
      maxHeight="lg"
      closeOnSelect
    >
      {REPORTS.map((report) => (
        <CustomMenu.MenuItem
          key={report.label}
          onClick={() => {
            // Excel file: hours stay numbers regardless of the spreadsheet locale (CSV is available via ?export=csv)
            window.location.href = IssueWorkLogService.reportExportUrl(workspaceSlug, projectId, "xlsx", report.group);
          }}
        >
          {report.label}
        </CustomMenu.MenuItem>
      ))}
    </CustomMenu>
  );
}
