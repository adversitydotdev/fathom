/** Shown inside the panel slot while the control streams in. */
export default function Loading() {
  return (
    <aside
      aria-busy="true"
      className="fixed inset-y-0 right-0 z-30 flex w-[min(100vw,42rem)] flex-col border-l bg-background shadow-2xl animate-in slide-in-from-right-8 fade-in-0 duration-200"
    >
      <div className="h-14 shrink-0 border-b" />
      <div className="flex flex-col gap-4 px-6 py-5">
        <div className="h-4 w-16 animate-pulse rounded bg-muted" />
        <div className="h-7 w-2/3 animate-pulse rounded bg-muted" />
        <div className="h-32 animate-pulse rounded-xl bg-muted" />
        <div className="h-48 animate-pulse rounded-xl bg-muted" />
      </div>
    </aside>
  );
}
