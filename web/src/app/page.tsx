import { redirect } from "next/navigation";
import { Suspense } from "react";

import { getPrograms } from "@/lib/data";

export default function Home() {
  return (
    <Suspense fallback={null}>
      <FirstProgram />
    </Suspense>
  );
}

async function FirstProgram(): Promise<React.ReactNode> {
  const programs = await getPrograms();
  if (programs.length === 0) {
    return (
      <main className="mx-auto max-w-md py-24 text-center">
        <h1 className="text-lg font-medium">Create your first program</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A program binds a system to a baseline. Create one through <code className="font-mono">POST /v1/programs</code>.
        </p>
      </main>
    );
  }
  redirect(`/programs/${programs[0].id}`);
}
