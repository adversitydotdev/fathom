"use client";

import {
  AlertTriangle,
  BookOpen,
  ClipboardCheck,
  FileText,
  FlaskConical,
  Gavel,
  Hexagon,
  LayoutDashboard,
  ListChecks,
  Paperclip,
  PauseCircle,
  Play,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";
import { cn } from "cn";

type Item = { label: string; icon: React.ComponentType<{ className?: string }>; href?: string };

export function Sidebar() {
  const { programId } = useParams<{ programId: string }>();
  const pathname = usePathname();
  const search = useSearchParams();
  const at = search.get("at");
  const base = `/programs/${programId}`;
  const withAt = (href: string) => (at ? `${href}?at=${at}` : href);

  const sections: { title?: string; items: Item[] }[] = [
    {
      items: [
        { label: "Overview", icon: LayoutDashboard, href: base },
        { label: "Controls", icon: ShieldCheck, href: `${base}/controls` },
        { label: "Requirements", icon: ListChecks },
        { label: "Tests", icon: FlaskConical },
        { label: "Evidence", icon: Paperclip },
      ],
    },
    {
      title: "Program",
      items: [
        { label: "Risks", icon: AlertTriangle },
        { label: "Exceptions", icon: PauseCircle },
        { label: "Findings", icon: Gavel },
        { label: "Policies", icon: FileText },
      ],
    },
    {
      title: "Organization",
      items: [
        { label: "Systems", icon: Server },
        { label: "Parties", icon: Users },
        { label: "Library", icon: BookOpen },
        { label: "Jobs", icon: Play },
      ],
    },
  ];

  const isActive = (href: string) => (href === base ? pathname === base : pathname.startsWith(href));

  return (
    <nav className="flex h-full flex-col gap-1 border-r bg-sidebar px-3 py-4 text-sm" aria-label="Main">
      <Link href={withAt(base)} className="mb-3 flex items-center gap-2 px-2 font-medium">
        <Hexagon className="size-5" aria-hidden />
        OpenGRC
      </Link>
      {sections.map((section, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          {section.title && <div className="px-2 pt-4 pb-1 text-xs text-muted-foreground">{section.title}</div>}
          {section.items.map(({ label, icon: Icon, href }) =>
            href ? (
              <Link
                key={label}
                href={withAt(href)}
                aria-current={isActive(href) ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
                  isActive(href) && "bg-sidebar-accent text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ) : (
              <span
                key={label}
                className="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-muted-foreground/60"
                title="Not built yet"
              >
                <Icon className="size-4" />
                {label}
              </span>
            ),
          )}
        </div>
      ))}
      <div className="mt-auto flex items-center gap-2 px-2 pt-4 text-xs text-muted-foreground">
        <ClipboardCheck className="size-3.5" aria-hidden />
        Status computed by the API
      </div>
    </nav>
  );
}

export function SidebarSkeleton() {
  return <div className="h-full border-r bg-sidebar" />;
}
