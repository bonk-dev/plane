/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): time logged on work items.
 */

export const MAX_WORKLOG_MINUTES = 24 * 60;

/**
 * Parses a human duration into minutes.
 * Accepts: "1h 30m", "1h30m", "2h", "45m", "1.5", "1,5h", "1:30".
 * A bare number means hours. Returns null when the input can't be parsed.
 */
export const parseDuration = (input: string): number | null => {
  const value = input.trim().toLowerCase().replace(",", ".");
  if (!value) return null;

  // 1:30 -> 1h 30m
  const clock = /^(\d+):([0-5]?\d)$/.exec(value);
  if (clock) return Number(clock[1]) * 60 + Number(clock[2]);

  // bare number -> hours
  if (/^\d+(\.\d+)?$/.test(value)) return Math.round(Number(value) * 60);

  const match = /^(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?$/.exec(value);
  if (!match || (match[1] === undefined && match[2] === undefined)) return null;
  const hours = match[1] ? Number(match[1]) : 0;
  const minutes = match[2] ? Number(match[2]) : 0;
  return Math.round(hours * 60 + minutes);
};

/** 150 -> "2h 30m", 45 -> "45m", 120 -> "2h" */
export const formatDuration = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
};

export const todayISO = (): string => {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
};
