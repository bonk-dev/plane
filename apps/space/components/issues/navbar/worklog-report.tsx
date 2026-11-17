/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): download the time report (estimate vs. logged time) of a published project.
 * Strings are intentionally hardcoded in Polish (not wired into @plane/i18n).
 */

import { FileSpreadsheet, FileText, Timer } from "lucide-react";
// plane imports
import { SitesIssueService } from "@plane/services";

type Props = {
  anchor: string;
};

const LINK_CLASS =
  "flex h-7 items-center gap-1 rounded-sm bg-layer-transparent px-2 text-11 font-medium text-primary hover:bg-layer-transparent-hover";

export function NavbarWorkLogReport({ anchor }: Props) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="hidden items-center gap-1 px-1 text-11 text-secondary sm:flex">
        <Timer className="size-3.5 shrink-0" />
        Raport czasu
      </span>
      <a
        href={SitesIssueService.workLogReportUrl(anchor, "xlsx")}
        title="Pobierz raport czasu (Excel)"
        aria-label="Pobierz raport czasu (Excel)"
        className={LINK_CLASS}
      >
        <FileSpreadsheet className="size-3.5 shrink-0" />
        XLSX
      </a>
      <a
        href={SitesIssueService.workLogReportUrl(anchor, "pdf")}
        title="Pobierz raport czasu (PDF z wykresami)"
        aria-label="Pobierz raport czasu (PDF z wykresami)"
        className={LINK_CLASS}
      >
        <FileText className="size-3.5 shrink-0" />
        PDF
      </a>
    </div>
  );
}
