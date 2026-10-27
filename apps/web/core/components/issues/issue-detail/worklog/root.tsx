/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Custom addition (fork): time logged on work items.
 * Strings are intentionally hardcoded in Polish (not wired into @plane/i18n).
 */

import { Fragment, useState } from "react";
import { Dialog, Transition } from "@headlessui/react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Timer } from "lucide-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { TrashIcon } from "@plane/propel/icons";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, Input } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useUser, useUserPermissions } from "@/hooks/store/user";
// services
import { IssueWorkLogService } from "@/services/issue/issue_worklog.service";
import type { TIssueWorkLog } from "@/services/issue/issue_worklog.service";
// local
import { MAX_WORKLOG_MINUTES, formatDuration, parseDuration, todayISO } from "./helpers";

const workLogService = new IssueWorkLogService();

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  /** false when the work item itself is read-only for the user (e.g. archived) */
  isEditable: boolean;
};

export const IssueWorkLogProperty = observer(function IssueWorkLogProperty(props: Props) {
  const { workspaceSlug, projectId, issueId, isEditable } = props;
  const [isOpen, setIsOpen] = useState(false);
  // store hooks
  const { data: currentUser } = useUser();
  const { allowPermissions } = useUserPermissions();
  const isProjectAdmin = allowPermissions(
    [EUserPermissions.ADMIN],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  const canLogTime =
    isEditable &&
    allowPermissions(
      [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
      EUserPermissionsLevel.PROJECT,
      workspaceSlug,
      projectId
    );
  // data
  const swrKey = workspaceSlug && projectId && issueId ? `ISSUE_WORKLOGS_${issueId}` : null;
  const { data: workLogs, mutate } = useSWR(swrKey, () => workLogService.list(workspaceSlug, projectId, issueId), {
    revalidateOnFocus: false,
  });
  const totalMinutes = (workLogs ?? []).reduce((sum, log) => sum + log.duration, 0);

  return (
    <>
      <SidebarPropertyListItem icon={Timer} label="Spędzony czas">
        <button
          type="button"
          data-testid="work-item-worklog-open"
          onClick={() => setIsOpen(true)}
          className={cn(
            "flex h-7.5 w-full items-center rounded-sm px-2 text-left text-body-xs-regular hover:bg-layer-transparent-hover",
            { "text-placeholder": totalMinutes === 0 }
          )}
        >
          {workLogs === undefined ? "…" : totalMinutes > 0 ? formatDuration(totalMinutes) : "Zaloguj czas"}
        </button>
      </SidebarPropertyListItem>

      <WorkLogModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        issueId={issueId}
        workLogs={workLogs ?? []}
        totalMinutes={totalMinutes}
        canLogTime={canLogTime}
        canDelete={(log) => isEditable && (isProjectAdmin || log.created_by === currentUser?.id)}
        onChanged={() => void mutate()}
      />
    </>
  );
});

type ModalProps = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  workLogs: TIssueWorkLog[];
  totalMinutes: number;
  canLogTime: boolean;
  canDelete: (log: TIssueWorkLog) => boolean;
  onChanged: () => void;
};

/**
 * Same markup as ModalCore from @plane/ui, plus `data-prevent-outside-click` on the dialog root:
 * the dialog is portaled outside the peek overview, so without it any click inside the dialog
 * (or on its backdrop) counts as an outside click and closes the peek together with the dialog.
 */
function WorkLogDialog({
  isOpen,
  onClose,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-30" onClose={onClose} data-prevent-outside-click>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-backdrop transition-opacity" />
        </Transition.Child>
        <div className="fixed inset-0 z-30 overflow-y-auto">
          <div className={EModalPosition.CENTER}>
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel
                className={cn(
                  "relative w-full transform rounded-lg bg-surface-1 text-left shadow-raised-200 transition-all",
                  EModalWidth.XXL
                )}
              >
                {children}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
}

const reportLinkClassName = "text-caption-sm-regular text-secondary underline underline-offset-2 hover:text-primary";

function WorkLogModal(props: ModalProps) {
  const {
    isOpen,
    onClose,
    workspaceSlug,
    projectId,
    issueId,
    workLogs,
    totalMinutes,
    canLogTime,
    canDelete,
    onChanged,
  } = props;
  const [duration, setDuration] = useState("");
  const [loggedDate, setLoggedDate] = useState(todayISO());
  const [description, setDescription] = useState("");
  const [durationError, setDurationError] = useState<string | undefined>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const resetForm = () => {
    setDuration("");
    setLoggedDate(todayISO());
    setDescription("");
    setDurationError(undefined);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const minutes = parseDuration(duration);
    if (minutes === null || minutes < 1) {
      setDurationError("Podaj czas, np. 1h 30m, 45m albo 1,5");
      return;
    }
    if (minutes > MAX_WORKLOG_MINUTES) {
      setDurationError("Maks. 24h na wpis. Sama liczba to godziny — minuty wpisz jako np. 90m");
      return;
    }
    setIsSubmitting(true);
    try {
      await workLogService.create(workspaceSlug, projectId, issueId, {
        duration: minutes,
        logged_date: loggedDate || todayISO(),
        description: description.trim(),
      });
      resetForm();
      onChanged();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Zapisano", message: `Zalogowano ${formatDuration(minutes)}` });
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Błąd", message: "Nie udało się zapisać czasu" });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (log: TIssueWorkLog) => {
    setDeletingId(log.id);
    try {
      await workLogService.remove(workspaceSlug, projectId, issueId, log.id);
      onChanged();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Błąd", message: "Nie udało się usunąć wpisu" });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <WorkLogDialog isOpen={isOpen} onClose={onClose}>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <div className="space-y-5 p-5">
          <h3 className="text-h4-medium text-secondary">
            Spędzony czas{totalMinutes > 0 ? ` — łącznie ${formatDuration(totalMinutes)}` : ""}
          </h3>

          {canLogTime && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="worklog-duration" className="mb-2 block text-secondary">
                    Czas
                    <span className="block text-caption-xs-regular text-tertiary">np. 1h 30m, 45m, 1,5</span>
                  </label>
                  <Input
                    id="worklog-duration"
                    type="text"
                    value={duration}
                    onChange={(e) => {
                      setDuration(e.target.value);
                      setDurationError(undefined);
                    }}
                    hasError={Boolean(durationError)}
                    placeholder="1h 30m"
                    className="w-full"
                  />
                  {durationError && (
                    <span className="text-caption-sm-regular text-danger-primary">{durationError}</span>
                  )}
                </div>
                <div>
                  <label htmlFor="worklog-date" className="mb-2 block text-secondary">
                    Dzień
                    <span className="block text-caption-xs-regular text-tertiary">&nbsp;</span>
                  </label>
                  <Input
                    id="worklog-date"
                    type="date"
                    value={loggedDate}
                    max={todayISO()}
                    onChange={(e) => setLoggedDate(e.target.value)}
                    className="w-full"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="worklog-description" className="mb-2 block text-secondary">
                  Co było robione
                  <span className="block text-caption-xs-regular text-tertiary">opcjonalnie</span>
                </label>
                <Input
                  id="worklog-description"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="np. walidacja formularza"
                  className="w-full"
                />
              </div>
            </div>
          )}

          <div className="space-y-1">
            <h6 className="text-body-xs-medium text-secondary">Wpisy</h6>
            {workLogs.length === 0 ? (
              <p className="text-body-xs-regular text-placeholder">Brak zalogowanego czasu.</p>
            ) : (
              <ul className="max-h-60 divide-y divide-subtle-1 overflow-y-auto">
                {workLogs.map((log) => (
                  <li key={log.id} className="flex items-center gap-3 py-2 text-body-xs-regular">
                    <span className="w-14 shrink-0 font-medium">{formatDuration(log.duration)}</span>
                    <div className="min-w-0 grow">
                      <div className="truncate">{log.description || <span className="text-placeholder">—</span>}</div>
                      <div className="text-tertiary">
                        {log.created_by_detail?.display_name ?? "?"} · {log.logged_date}
                      </div>
                    </div>
                    {canDelete(log) && (
                      <button
                        type="button"
                        aria-label="Usuń wpis"
                        disabled={deletingId === log.id}
                        onClick={() => void handleDelete(log)}
                        className="grid size-7 shrink-0 place-items-center rounded-sm text-tertiary hover:bg-layer-transparent-hover hover:text-danger-primary disabled:opacity-50"
                      >
                        <TrashIcon className="size-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <a
              className={reportLinkClassName}
              href={IssueWorkLogService.reportExportUrl(workspaceSlug, projectId, "xlsx", "person")}
            >
              Excel: osoba – zadanie – estymata – czas
            </a>
            <a
              className={reportLinkClassName}
              href={IssueWorkLogService.reportExportUrl(workspaceSlug, projectId, "xlsx", "issue")}
            >
              Excel: estymata vs. czas (projekt)
            </a>
            <a
              className={reportLinkClassName}
              href={IssueWorkLogService.reportExportUrl(workspaceSlug, projectId, "xlsx", "member")}
            >
              Excel: czas per osoba
            </a>
            <a
              className={reportLinkClassName}
              href={IssueWorkLogService.reportExportUrl(workspaceSlug, projectId, "xlsx")}
            >
              Excel: wszystkie wpisy
            </a>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t-[0.5px] border-subtle px-5 py-4">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Zamknij
          </Button>
          {canLogTime && (
            <Button variant="primary" size="lg" type="submit" loading={isSubmitting}>
              {isSubmitting ? "Zapisywanie…" : "Dodaj czas"}
            </Button>
          )}
        </div>
      </form>
    </WorkLogDialog>
  );
}
