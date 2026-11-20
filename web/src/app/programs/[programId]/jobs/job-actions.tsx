"use client";

import { FileCode2, FileText, GitBranch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { triggerGitExport, triggerRender, type ActionState } from "@/lib/actions";

/** Polls server data while any job is queued or running so completion appears automatically. */
export function JobsAutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), 1200);
    return () => clearInterval(id);
  }, [active, router]);
  return null;
}

export function JobActions({ programId, frameworkId }: { programId: string; frameworkId?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3 pt-1">
      {frameworkId && (
        <ActionTrigger
          label="Render OSCAL 1.2.3"
          icon={<FileCode2 className="size-3.5" aria-hidden />}
          run={() => triggerRender(programId, "oscal", frameworkId)}
        />
      )}
      <ActionTrigger
        label="Render Narrative SSP"
        icon={<FileText className="size-3.5" aria-hidden />}
        run={() => triggerRender(programId, "ssp")}
      />
      <ActionTrigger
        label="Run Git export"
        icon={<GitBranch className="size-3.5" aria-hidden />}
        run={() => triggerGitExport()}
      />
    </div>
  );
}

function ActionTrigger({
  label,
  icon,
  run,
}: {
  label: string;
  icon: React.ReactNode;
  run: () => Promise<ActionState>;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [state, setState] = useState<ActionState>({});

  return (
    <div className="flex items-center gap-2">
      <LoadingButton
        variant="outline"
        size="sm"
        className="h-8 gap-1.5 px-3 text-xs"
        loading={pending}
        disabled={pending}
        onClick={() =>
          start(async () => {
            const res = await run();
            setState(res);
            if (res.jobId) {
              // Fast jobs (e.g. SSP render ~350ms) often finish right after 202 Accepted.
              router.refresh();
              setTimeout(() => router.refresh(), 600);
              setTimeout(() => router.refresh(), 1800);
            }
          })
        }
      >
        {!pending && icon}
        {label}
      </LoadingButton>
      {state.jobId && (
        <span className="font-mono text-xs text-met-ink" title={state.jobId}>
          Queued
        </span>
      )}
      {state.error && <span className="text-xs text-gap-ink">{state.error}</span>}
    </div>
  );
}
