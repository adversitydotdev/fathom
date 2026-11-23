"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "cn";

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("min-w-0 space-y-2.5 text-sm leading-relaxed break-words", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-semibold text-foreground pt-1 first:pt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold text-foreground pt-2 first:pt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-foreground pt-2 first:pt-0">
              {children}
            </h3>
          ),
          p: ({ children }) => <p className="text-foreground/95">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 text-foreground/90">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 text-foreground/90">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-agent/50 pl-3 text-xs text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="border-border my-2" />,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="underline decoration-foreground/40 underline-offset-2 hover:text-foreground"
            >
              {children}
            </a>
          ),
          code: ({ className: codeCls, children }) => {
            const isBlock = Boolean(codeCls?.includes("language-"));
            if (isBlock) {
              return (
                <code className={cn("font-mono text-xs leading-relaxed text-foreground", codeCls)}>
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[12px] text-foreground">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-xl border bg-muted/40 p-3 font-mono text-xs">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-left text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b bg-muted/40 text-xs font-medium text-muted-foreground">
              {children}
            </thead>
          ),
          tbody: ({ children }) => <tbody className="divide-y">{children}</tbody>,
          th: ({ children }) => <th className="px-2.5 py-1.5 font-medium">{children}</th>,
          td: ({ children }) => <td className="px-2.5 py-1.5">{children}</td>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
