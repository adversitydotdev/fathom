"use client";

import { Loader2, Play } from "lucide-react";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";

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
      <Button
        variant="outline"
        size="sm"
        disabled={pending}
        onClick={() => start(async () => setState(await runTest(testId, implementationId)))}
      >
        {pending ? <Loader2 className="animate-spin" /> : <Play />}
        Run
      </Button>
    </span>
  );
}
