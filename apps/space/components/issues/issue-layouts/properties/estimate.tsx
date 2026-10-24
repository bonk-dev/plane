/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): estimates shown in published projects.
 */

import { useParams } from "next/navigation";
// plane imports
import { useTranslation } from "@plane/i18n";
import { EstimatePropertyIcon } from "@plane/propel/icons";
import { Tooltip } from "@plane/propel/tooltip";
// hooks
import { usePublicEstimate } from "@/hooks/use-public-estimate";

export function IssueBlockEstimate({ estimatePointId }: { estimatePointId: string | null | undefined }) {
  const { t } = useTranslation();
  const { anchor } = useParams();
  const { getEstimateLabel } = usePublicEstimate(anchor?.toString());
  const label = getEstimateLabel(estimatePointId);

  if (!label) return null;

  return (
    <Tooltip tooltipHeading={t("common.estimate")} tooltipContent={label}>
      <div className="flex h-full items-center gap-1 rounded-sm border-[0.5px] border-strong px-2 py-0.5 text-11">
        <EstimatePropertyIcon className="size-3 flex-shrink-0" />
        <span>{label}</span>
      </div>
    </Tooltip>
  );
}
