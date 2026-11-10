"use client";

import { Play } from "lucide-react";
import { useState, useTransition } from "react";

import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";

import { runTest, type RunState } from "./actions";

export function RunTestButton({ testId, implementationId }: { testId: string; implementationId: string }) {
  const [pending, start] = useTransition();
  const [state, setState] = useState<RunState>({});

  if (state.jobId) {
    return (
      <span className="text-xs text-muted-foreground" title={state.jobId}>
        Queued
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2">
      {state.error && <span className="text-xs text-gap-ink">{state.error}</span>}
      <LoadingButton
        variant="outline"
        size="sm"
        className="h-7 gap-1 px-2.5 text-xs"
        loading={pending}
        disabled={pending}
        onClick={() => start(async () => setState(await runTest(testId, implementationId)))}
      >
        {!pending && <Play className="size-3" aria-hidden />}
        Run
      </LoadingButton>
    </span>
  );
}
