/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): time estimates in Community.
 * Accepts the same formats as time logging ("2h", "1h 30m", "45m", "1,5") and stores minutes.
 */

import { useEffect, useRef, useState } from "react";
// local
import { formatDuration, parseDuration } from "@/components/issues/issue-detail/worklog/helpers";

type TEstimateTimeInputProps = {
  /** minutes */
  value?: string;
  handleEstimateInputValue: (value: string) => void;
};

export function EstimateTimeInput(props: TEstimateTimeInputProps) {
  const { value, handleEstimateInputValue } = props;
  const [text, setText] = useState("");
  // last value sent to the form, to tell our own updates apart from external ones
  const lastEmitted = useRef<string | undefined>(undefined);

  // the edit form sets the existing value after mount, so follow external changes
  useEffect(() => {
    if (value === lastEmitted.current) return;
    lastEmitted.current = value;
    setText(value && !isNaN(Number(value)) ? formatDuration(Number(value)) : (value ?? ""));
  }, [value]);

  return (
    <input
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const minutes = parseDuration(e.target.value);
        // unparseable input is passed through as-is so the form shows its "numeric" validation error
        const next = minutes === null ? e.target.value : String(minutes);
        lastEmitted.current = next;
        handleEstimateInputValue(next);
      }}
      className="w-full border-none bg-transparent px-2 py-2 text-13 focus:border-0 focus:ring-0 focus:outline-none"
      placeholder="np. 2h, 1h 30m, 4"
      // same as the upstream number input: focus the field when a new point row opens
      // oxlint-disable-next-line jsx_a11y/no-autofocus
      autoFocus
    />
  );
}
