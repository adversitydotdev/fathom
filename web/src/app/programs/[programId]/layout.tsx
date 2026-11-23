import { Suspense } from "react";

import { AgentProvider, AgentSystemSync, AssistantTriggerButton } from "@/components/agent/assistant-drawer";
import { AtPicker, ProgramSwitcher } from "@/components/shell/header-controls";
import { PanelOriginTracker } from "@/components/shell/side-panel";
import { Sidebar, SidebarSkeleton } from "@/components/shell/sidebar";
import { ThemeToggle } from "@/components/theme";
import { apiMocking } from "@/lib/env";
import { getProgram, getPrograms, getSystem } from "@/lib/data";

export default function ProgramLayout({ children, panel, params }: LayoutProps<"/programs/[programId]">) {
  return (
    <AgentProvider>
      <div className="grid min-h-dvh grid-cols-[14rem_minmax(0,1fr)]">
        <div className="border-r bg-sidebar">
          <aside className="sticky top-0 h-dvh">
            <Suspense fallback={<SidebarSkeleton />}>
              <Sidebar footer={apiMocking ? <MockBadge /> : undefined} />
            </Suspense>
          </aside>
        </div>
        <div className="flex min-w-0 flex-col">
          <header className="sticky top-0 z-10 flex h-14 items-center gap-2 border-b bg-background/85 px-6 backdrop-blur lg:px-10">
            <Suspense fallback={<div className="h-8 w-56 rounded-md border" />}>
              <Switcher params={params} />
            </Suspense>
            <div className="flex-1" />
            <Suspense fallback={<div className="h-8 w-36 rounded-md border" />}>
              <AtPicker />
            </Suspense>
            <AssistantTriggerButton />
            <ThemeToggle />
          </header>
          <main className="flex-1 px-6 py-8 lg:px-10">{children}</main>
          {panel}
          <Suspense fallback={null}>
            <PanelOriginTracker />
          </Suspense>
        </div>
      </div>
    </AgentProvider>
  );
}

async function Switcher({ params }: { params: LayoutProps<"/programs/[programId]">["params"] }) {
  const { programId } = await params;
  const [programs, program] = await Promise.all([getPrograms(), getProgram(programId)]);
  const system = await getSystem(program.system_ref);
  return (
    <>
      <AgentSystemSync systemId={system.id} />
      <ProgramSwitcher
        programs={programs.filter((p) => p.system_ref === program.system_ref).map((p) => ({ id: p.id, name: p.name ?? p.id }))}
        current={program.id}
        systemName={system.name ?? system.id}
      />
    </>
  );
}

function MockBadge() {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      title="OGRL_API_MOCKING=enabled: /v1 is served from src/mocks"
    >
      <span className="size-1.5 rounded-full bg-waived" aria-hidden />
      Fixtures · no auth
    </span>
  );
}
