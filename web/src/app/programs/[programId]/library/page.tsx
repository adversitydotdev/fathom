import type { Metadata } from "next";
import { BookOpen, ExternalLink, GitCommitHorizontal } from "lucide-react";

import { StatusBadge } from "@/components/spectrumui/status-badge";
import { Eyebrow, PageTitle } from "@/components/typography";
import { getControls, getFrameworks, getLibraryPin, getProgram } from "@/lib/data";

import { LibraryPullButton } from "./library-pull-button";

export const metadata: Metadata = { title: "Library" };

export default async function LibraryPage({
  params,
}: {
  params: Promise<{ programId: string }>;
}) {
  const { programId } = await params;

  const program = await getProgram(programId);
  const [pin, frameworks, controls] = await Promise.all([
    getLibraryPin(),
    getFrameworks(),
    getControls(),
  ]);

  const standardControls = controls.filter((c) => c.origin === "standard").length;
  const customControls = controls.filter((c) => c.origin === "custom").length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageTitle
        eyebrow={program.name}
        title="Library"
        aside={
          <a
            href="https://ogrl.adversity.dev/library/"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 font-mono text-[11px] tracking-[0.08em] text-muted-foreground uppercase transition-colors hover:border-foreground/40 hover:text-foreground"
          >
            Browse public catalog
            <ExternalLink className="size-3" aria-hidden />
          </a>
        }
      />

      <section className="flex flex-col gap-4 rounded-2xl border bg-card p-6" aria-label="Pinned library revision">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <Eyebrow>Pinned ogrl-library revision</Eyebrow>
            <div className="flex flex-wrap items-center gap-2.5 pt-1">
              <span className="font-display text-3xl tracking-[-0.02em]">
                {pin.version ? `v${pin.version}` : "unpinned"}
              </span>
              {pin.version && <StatusBadge tone="met">pinned</StatusBadge>}
            </div>
          </div>

          <LibraryPullButton currentVersion={pin.version ?? "0.2.0"} />
        </div>

        <div className="grid grid-cols-2 gap-3 border-t pt-4 md:grid-cols-4">
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">Commit</span>
            <span className="inline-flex items-center gap-1.5 font-mono text-xs">
              <GitCommitHorizontal className="size-3.5 text-muted-foreground" aria-hidden />
              {pin.commit ? pin.commit.slice(0, 12) : "—"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">Source ID</span>
            <span className="font-mono text-xs">{pin.id}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
              Installed frameworks
            </span>
            <span className="font-mono text-xs tabular-nums">{frameworks.length}</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
              Controls in catalog
            </span>
            <span className="font-mono text-xs tabular-nums">
              {standardControls} standard · {customControls} custom
            </span>
          </div>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <Eyebrow>Installed frameworks</Eyebrow>
        <div className="grid gap-3 md:grid-cols-2">
          {frameworks.map((fw) => (
            <div key={fw.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <BookOpen className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div>
                    <h2 className="text-base font-medium">{fw.name}</h2>
                    <p className="font-mono text-xs text-muted-foreground">
                      {fw.publisher} · v{fw.version}
                    </p>
                  </div>
                </div>
                <StatusBadge tone={fw.reproduction === "permitted" ? "met" : "contribution"}>
                  {fw.reproduction}
                </StatusBadge>
              </div>
              <div className="border-t pt-2.5 font-mono text-[11px] text-muted-foreground">{fw.id}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
