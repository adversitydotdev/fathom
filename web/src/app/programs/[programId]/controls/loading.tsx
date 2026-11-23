export default function Loading() {
  return (
    <div className="mx-auto flex max-w-6xl animate-pulse flex-col gap-6" aria-busy="true" aria-label="Loading">
      <div className="h-14 w-80 rounded-xl bg-muted" />
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 rounded-xl bg-muted" />
        ))}
      </div>
      <div className="h-40 rounded-xl bg-muted" />
      <div className="h-64 rounded-xl bg-muted" />
    </div>
  );
}
