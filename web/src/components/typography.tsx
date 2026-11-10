import { cn } from "cn";

/** Mono uppercase label with a corner bracket, as Spectrum marks sections. */
export function Eyebrow({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 font-mono text-[11px] leading-none font-medium tracking-[0.14em] text-muted-foreground uppercase",
        "before:size-2 before:shrink-0 before:border-t before:border-l before:border-foreground/50 before:content-['']",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Display-serif page title with an optional eyebrow and supporting line. */
export function PageTitle({
  eyebrow,
  title,
  aside,
  children,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  aside?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3">
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h1 className="font-display text-4xl leading-[1.05] tracking-[-0.02em]">{title}</h1>
        {aside}
      </div>
      {children}
    </div>
  );
}
