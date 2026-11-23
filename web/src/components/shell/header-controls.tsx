"use client";

import { CalendarDays, ChevronsUpDown, X } from "lucide-react";
import { cn } from "cn";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import { Spinner } from "@/components/spectrumui/spinner-dependencies";

type ProgramOption = { id: string; name: string };

export function ProgramSwitcher({
  programs,
  current,
  systemName,
}: {
  programs: ProgramOption[];
  current: string;
  systemName: string;
}) {
  const router = useRouter();
  const search = useSearchParams();
  const [pending, start] = useTransition();
  return (
    <label className="relative flex h-8 items-center gap-2 rounded-md border bg-card pr-2 pl-3 text-sm shadow-xs transition-colors hover:bg-muted">
      {pending && <Spinner size="small" className="size-3.5 text-muted-foreground" />}
      <span className="text-muted-foreground">{systemName}</span>
      <span className="text-muted-foreground/50">/</span>
      <select
        className="cursor-pointer appearance-none bg-transparent pr-5 font-medium outline-none"
        value={current}
        aria-label="Program"
        onChange={(e) => {
          const at = search.get("at");
          start(() => router.push(`/programs/${e.target.value}${at ? `?at=${at}` : ""}`));
        }}
      >
        {programs.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <ChevronsUpDown className="pointer-events-none absolute right-2 size-3.5 text-muted-foreground" aria-hidden />
    </label>
  );
}

/**
 * The evaluation date. RFC 0004: past status is computed from the revisions
 * in force then, so this is a view of the past, not today's objects re-dated.
 * The native date input sits invisibly over the pill so the pill can read
 * "Today" instead of the browser's empty mm/dd/yyyy placeholder.
 */
export function AtPicker() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [pending, start] = useTransition();
  const at = search.get("at") ?? "";

  const set = (value: string) => {
    const next = new URLSearchParams(search);
    if (value) next.set("at", value);
    else next.delete("at");
    const qs = next.toString();
    start(() => router.replace(qs ? `${pathname}?${qs}` : pathname));
  };

  return (
    <div
      className={cn(
        "relative flex h-8 items-center gap-1.5 rounded-md border bg-card px-2.5 text-sm shadow-xs transition-colors hover:bg-muted",
        at && "border-waived/50 bg-waived-soft text-waived-ink hover:bg-waived-soft",
      )}
    >
      {pending ? <Spinner size="small" className="size-4" /> : <CalendarDays className="size-4 opacity-70" aria-hidden />}
      <span className="text-muted-foreground">{at ? "Viewing" : "As of"}</span>
      <span className="font-medium tabular-nums">{at || "Today"}</span>
      <input
        type="date"
        aria-label="Evaluation date"
        value={at}
        onChange={(e) => set(e.target.value)}
        onClick={(e) => e.currentTarget.showPicker?.()}
        className="absolute inset-0 cursor-pointer opacity-0 [color-scheme:light] dark:[color-scheme:dark]"
      />
      {at && (
        <button
          type="button"
          onClick={() => set("")}
          className="relative z-10 -mr-1 ml-0.5 rounded p-0.5 hover:bg-waived/20"
          aria-label="Evaluate now"
          title="Back to today"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}
