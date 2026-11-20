"use client";

import { Download } from "lucide-react";
import { useState, useTransition } from "react";

import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";
import { triggerLibraryPull, type ActionState } from "@/lib/actions";

export function LibraryPullButton({ currentVersion }: { currentVersion: string }) {
  const [version, setVersion] = useState(currentVersion);
  const [pending, start] = useTransition();
  const [state, setState] = useState<ActionState>({});

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor="library-version">
        Library version
      </label>
      <input
        id="library-version"
        type="text"
        value={version}
        onChange={(e) => setVersion(e.target.value)}
        placeholder="0.2.0"
        className="h-8 w-28 rounded-lg border bg-background px-2.5 font-mono text-xs"
      />
      <LoadingButton
        variant="outline"
        size="sm"
        className="h-8 gap-1.5 px-3 text-xs"
        loading={pending}
        disabled={pending || !version.trim()}
        onClick={() => start(async () => setState(await triggerLibraryPull(version.trim())))}
      >
        {!pending && <Download className="size-3.5" aria-hidden />}
        Pull revision
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
