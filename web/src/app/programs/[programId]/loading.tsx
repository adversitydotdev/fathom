/** Mirrors the overview's layout so the page doesn't jump when it streams in. */
export default function Loading() {
  return (
    <div className="mx-auto flex max-w-6xl animate-pulse flex-col gap-6" aria-busy="true" aria-label="Loading">
      <div className="flex flex-col gap-2">
        <div className="h-3 w-24 rounded bg-muted" />
        <div className="h-7 w-64 rounded-md bg-muted" />
        <div className="h-4 w-48 rounded bg-muted" />
      </div>
      <div className="flex h-44 items-center gap-5 rounded-xl border bg-card px-5">
        <div className="size-28 rounded-full border-[10px] border-muted" />
        <div className="flex flex-col gap-2">
          <div className="h-5 w-40 rounded bg-muted" />
          <div className="h-4 w-32 rounded bg-muted" />
        </div>
      </div>
      <div className="h-36 rounded-xl border bg-card" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="h-80 rounded-xl border bg-card" />
        <div className="h-80 rounded-xl border bg-card" />
      </div>
    </div>
  );
}
