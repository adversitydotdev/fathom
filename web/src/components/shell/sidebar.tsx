"use client";

import {
  AlertTriangle,
  BookOpen,
  FileText,
  FlaskConical,
  Gavel,
  LayoutDashboard,
  ListChecks,
  Paperclip,
  PauseCircle,
  Play,
  Plug,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";
import { cn } from "cn";
import { OgrlMark } from "@/components/brand-mark";

type Item = { label: string; icon: React.ComponentType<{ className?: string }>; href: string };

export function Sidebar({ footer }: { footer?: React.ReactNode }) {
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
        { label: "Requirements", icon: ListChecks, href: `${base}/requirements` },
        { label: "Tests", icon: FlaskConical, href: `${base}/tests` },
        { label: "Evidence", icon: Paperclip, href: `${base}/evidence` },
      ],
    },
    {
      title: "Program",
      items: [
        { label: "Risks", icon: AlertTriangle, href: `${base}/risks` },
        { label: "Exceptions", icon: PauseCircle, href: `${base}/exceptions` },
        { label: "Findings", icon: Gavel, href: `${base}/findings` },
        { label: "Policies", icon: FileText, href: `${base}/policies` },
      ],
    },
    {
      title: "Organization",
      items: [
        { label: "Systems", icon: Server, href: `${base}/systems` },
        { label: "Parties", icon: Users, href: `${base}/parties` },
        { label: "Integrations", icon: Plug, href: `${base}/integrations` },
        { label: "Library", icon: BookOpen, href: `${base}/library` },
        { label: "Jobs", icon: Play, href: `${base}/jobs` },
      ],
    },
  ];

  const isActive = (href: string) => (href === base ? pathname === base : pathname.startsWith(href));

  return (
    <nav className="flex h-full flex-col gap-1 px-3 py-4 text-sm" aria-label="Main">
      <Link href={withAt(base)} className="mb-3 flex h-8 items-center gap-2 px-2">
        <OgrlMark className="size-5 shrink-0 text-primary" aria-hidden />
        <span className="text-base font-semibold tracking-tight">OGRL</span>
      </Link>
      {sections.map((section, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          {section.title && <div className="px-2 pt-5 pb-1 text-xs font-medium text-muted-foreground">{section.title}</div>}
          {section.items.map(({ label, icon: Icon, href }) => {
            const active = isActive(href);
            return (
              <Link
                key={label}
                href={withAt(href)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-foreground/75 transition-colors hover:bg-foreground/5 hover:text-foreground",
                  active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                )}
              >
                <Icon className={cn("size-4 text-muted-foreground", active && "text-sidebar-accent-foreground")} />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
      {footer && <div className="mt-auto px-2 pt-4">{footer}</div>}
    </nav>
  );
}

export function SidebarSkeleton() {
  return <div className="h-full" />;
}
