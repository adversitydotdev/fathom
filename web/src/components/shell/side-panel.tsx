"use client";

import { Maximize2, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * Right-side detail panel for intercepted routes. It is not modal: the list
 * behind stays usable, so clicking another row swaps the panel's content.
 * Closing returns to the page the panel was opened from.
 */

const DETAIL = /^\/programs\/[^/]+\/controls\/[^/]+$/;

/** True for URLs that a soft navigation would open in the panel. */
export function isPanelRoute(pathname: string) {
  return DETAIL.test(pathname);
}
let origin: string | null = null;

/**
 * The list page's location. While the panel is open the URL is the panel's,
 * so URL-driven list filters read (and write) the page underneath instead.
 * Changing a filter therefore navigates back to the list, closing the panel.
 */
export function useListLocation(): { pathname: string; search: URLSearchParams } {
  const pathname = usePathname();
  const search = useSearchParams();
  if (isPanelRoute(pathname) && origin) {
    const u = new URL(origin, "http://local");
    return { pathname: u.pathname, search: u.searchParams };
  }
  return { pathname, search: new URLSearchParams(search.toString()) };
}

/** Mounted in the program layout: remembers the last URL that was not a panel route. */
export function PanelOriginTracker() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    if (!DETAIL.test(pathname)) {
      const qs = search.toString();
      origin = qs ? `${pathname}?${qs}` : pathname;
    }
  }, [pathname, search]);
  return null;
}

export function SidePanel({
  label,
  fullHref,
  fallbackHref,
  children,
}: {
  /** Accessible name; the panel heading should carry `id="control-panel-title"` when present. */
  label: string;
  /** The same URL as a full page. A plain anchor, so the load is not intercepted again. */
  fullHref: string;
  /** Where to go on close when the opening page is unknown. */
  fallbackHref: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const ref = useRef<HTMLElement>(null);
  const close = () => router.push(origin ?? fallbackHref, { scroll: false });

  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Leave Escape to a dialog opened from inside the panel.
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) return;
      router.push(origin ?? fallbackHref, { scroll: false });
    };
    // Capture phase: Radix closes its dialogs on a capturing listener too, and
    // ours is registered first, so it still sees the dialog open.
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [router, fallbackHref]);

  return (
    <aside
      ref={ref}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-label={label}
      className="fixed inset-y-0 right-0 z-30 flex w-[min(100vw,42rem)] flex-col border-l bg-background shadow-2xl outline-none animate-in slide-in-from-right-8 fade-in-0 duration-200"
    >
      <div className="flex h-14 shrink-0 items-center justify-end gap-1 border-b px-4">
        <a
          href={fullHref}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Maximize2 className="size-3.5" aria-hidden />
          Open full page
        </a>
        <button
          type="button"
          onClick={close}
          aria-label="Close panel"
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
    </aside>
  );
}
