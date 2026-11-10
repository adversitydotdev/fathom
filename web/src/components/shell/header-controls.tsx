"use client";

import { CalendarDays, ChevronDown, RotateCcw } from "lucide-react";
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
    <label className="relative flex h-8 items-center gap-2 rounded-full border bg-card pr-2 pl-3.5 text-sm">
      {pending && <Spinner size="small" className="size-3.5 text-muted-foreground" />}
      <span className="text-muted-foreground">{systemName} /</span>
      <select
        className="appearance-none bg-transparent pr-5 font-medium outline-none"
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
      <ChevronDown className="pointer-events-none absolute right-2 size-3.5 text-muted-foreground" aria-hidden />
    </label>
  );
}

/**
 * The evaluation date. RFC 0004: past status is computed from the revisions
 * in force then, so this is a view of the past, not today's objects re-dated.
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
    <div className="flex h-8 items-center gap-1.5 rounded-full border bg-card px-3.5 text-sm">
      {pending ? (
        <Spinner size="small" className="size-4 text-muted-foreground" />
      ) : (
        <CalendarDays className="size-4 text-muted-foreground" aria-hidden />
      )}
      <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">At</span>
      <input
        type="date"
        aria-label="Evaluation date"
        value={at}
        onChange={(e) => set(e.target.value)}
        className="bg-transparent font-mono text-xs outline-none [color-scheme:light] dark:[color-scheme:dark]"
      />
      {at ? (
        <button type="button" onClick={() => set("")} className="text-muted-foreground hover:text-foreground" aria-label="Evaluate now">
          <RotateCcw className="size-3.5" />
        </button>
      ) : (
        <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">now</span>
      )}
    </div>
  );
}
