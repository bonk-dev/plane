/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): estimates shown in published projects.
 */

import useSWR from "swr";
// plane imports
import { SitesIssueService } from "@plane/services";
import { convertMinutesToHoursMinutesString } from "@plane/utils";

const issueService = new SitesIssueService();

/** Returns a function that maps an issue's estimate_point id to its display value ("2h", "5", "M"). */
export const usePublicEstimate = (anchor: string | undefined) => {
  // one request per anchor, shared by every card thanks to SWR deduplication
  const { data } = useSWR(
    anchor ? `PUBLIC_PROJECT_ESTIMATE_${anchor}` : null,
    () => issueService.getProjectEstimate(anchor!),
    { revalidateOnFocus: false }
  );

  const getEstimateLabel = (estimatePointId: string | null | undefined): string | undefined => {
    if (!estimatePointId || !data) return undefined;
    const point = data.points.find((p) => p.id === estimatePointId);
    if (!point) return undefined;
    return data.type === "time" ? convertMinutesToHoursMinutesString(Number(point.value)).trim() : point.value;
  };

  return { getEstimateLabel };
};
