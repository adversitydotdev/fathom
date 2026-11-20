import { Suspense } from "react";

import { AtPicker, ProgramSwitcher } from "@/components/shell/header-controls";
import { Sidebar, SidebarSkeleton } from "@/components/shell/sidebar";
import { ThemeToggle } from "@/components/theme";
import { apiMocking } from "@/lib/env";
import { getProgram, getPrograms, getSystem } from "@/lib/data";

export default function ProgramLayout({ children, params }: LayoutProps<"/programs/[programId]">) {
  return (
    <div className="grid min-h-dvh grid-cols-[13rem_minmax(0,1fr)]">
      <aside className="sticky top-0 h-dvh">
        <Suspense fallback={<SidebarSkeleton />}>
          <Sidebar />
        </Suspense>
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-2 border-b bg-background/80 px-6 py-3 backdrop-blur">
          {apiMocking && (
            <span
              className="rounded-full border border-waived/40 bg-waived-soft px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] text-waived-ink uppercase"
              title="OGRL_API_MOCKING=enabled: /v1 is served from src/mocks"
            >
              Fixtures · no auth
            </span>
          )}
          <div className="flex-1" />
          <Suspense fallback={<div className="h-8 w-56 rounded-full border" />}>
            <Switcher params={params} />
          </Suspense>
          <Suspense fallback={<div className="h-8 w-44 rounded-full border" />}>
            <AtPicker />
          </Suspense>
          <ThemeToggle />
        </header>
        <main className="flex-1 px-6 py-8 lg:px-10">{children}</main>
      </div>
    </div>
  );
}

async function Switcher({ params }: { params: LayoutProps<"/programs/[programId]">["params"] }) {
  const { programId } = await params;
  const [programs, program] = await Promise.all([getPrograms(), getProgram(programId)]);
  const system = await getSystem(program.system_ref);
  return (
    <ProgramSwitcher
      programs={programs.filter((p) => p.system_ref === program.system_ref).map((p) => ({ id: p.id, name: p.name ?? p.id }))}
      current={program.id}
      systemName={system.name ?? system.id}
    />
  );
}
