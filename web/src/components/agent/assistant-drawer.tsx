"use client";

import {
  ArrowUpRight,
  Check,
  LoaderCircle,
  RotateCcw,
  Send,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { cn } from "cn";

import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";

type AgentStatus = {
  enabled: boolean;
  model?: string | null;
  provider?: string | null;
  actor_id: string;
  hint?: string | null;
};

type ToolTrace = {
  name: string;
  done: boolean;
};

type CreatedDraft = {
  object_type: string;
  id: string;
  control_ref?: string;
  label: string;
  /** query_source drafts (RFC 0006 section 9): the unsaved definition, and the rule that reads it. */
  definition?: Record<string, unknown>;
  rule?: Record<string, unknown>;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  tools?: ToolTrace[];
  drafts?: CreatedDraft[];
  error?: string;
  streaming?: boolean;
};

type AgentContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  ask: (prompt: string) => void;
  setSystemId: (id: string) => void;
  status: AgentStatus | null;
};

const AgentContext = React.createContext<AgentContextValue | null>(null);

export function useAgent() {
  const ctx = React.useContext(AgentContext);
  if (!ctx) throw new Error("useAgent must be used inside AgentProvider");
  return ctx;
}

export function AgentSystemSync({ systemId }: { systemId: string }) {
  const { setSystemId } = useAgent();
  React.useEffect(() => {
    setSystemId(systemId);
  }, [setSystemId, systemId]);
  return null;
}

function readRouteContext(): { programId: string; controlId?: string; route?: string } {
  if (typeof window === "undefined") return { programId: "" };
  const route = window.location.pathname;
  const progMatch = route.match(/^\/programs\/([^/]+)/);
  const ctrlMatch = route.match(/^\/programs\/[^/]+\/controls\/([^/]+)/);
  return {
    programId: progMatch ? decodeURIComponent(progMatch[1]) : "",
    controlId: ctrlMatch ? decodeURIComponent(ctrlMatch[1]) : undefined,
    route,
  };
}

export function AgentProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [systemId, setSystemId] = React.useState<string | undefined>(undefined);

  const [open, setOpen] = React.useState(false);
  const [status, setStatus] = React.useState<AgentStatus | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let active = true;
    fetch("/api/agent/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((data: AgentStatus | null) => {
        if (active && data) setStatus(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = React.useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text || streaming) return;

      const history = messages
        .filter((m) => !m.error && m.content.trim())
        .map((m) => ({ role: m.role, content: m.content }));

      const userId = `u-${Date.now()}`;
      const assistantId = `a-${Date.now() + 1}`;
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: text },
        { id: assistantId, role: "assistant", content: "", tools: [], drafts: [], streaming: true },
      ]);
      setInput("");
      setStreaming(true);

      try {
        const routeCtx = readRouteContext();
        const res = await fetch("/api/agent/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            history,
            context: {
              program_id: routeCtx.programId || undefined,
              system_id: systemId,
              control_id: routeCtx.controlId,
              route: routeCtx.route,
            },
          }),
        });

        if (!res.ok || !res.body) {
          const errText = await res.text().catch(() => `HTTP ${res.status}`);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, streaming: false, error: errText || `HTTP ${res.status}` } : m,
            ),
          );
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let sawDraft = false;

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            const dataLine = frame
              .split("\n")
              .find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            const ev = JSON.parse(dataLine.slice(6)) as {
              type: string;
              text?: string;
              name?: string;
              message?: string;
              object_type?: string;
              id?: string;
              control_ref?: string;
              label?: string;
              definition?: Record<string, unknown>;
              rule?: Record<string, unknown>;
              drafts?: CreatedDraft[];
            };

            if (ev.type === "delta" && ev.text) {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + ev.text } : m)),
              );
            } else if (ev.type === "tool_call" && ev.name) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, tools: [...(m.tools ?? []), { name: ev.name!, done: false }] }
                    : m,
                ),
              );
            } else if (ev.type === "tool_result" && ev.name) {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId) return m;
                  const next = [...(m.tools ?? [])];
                  for (let i = next.length - 1; i >= 0; i--) {
                    if (next[i].name === ev.name && !next[i].done) {
                      next[i] = { ...next[i], done: true };
                      break;
                    }
                  }
                  return { ...m, tools: next };
                }),
              );
            } else if (ev.type === "draft" && ev.id && ev.object_type) {
              sawDraft = true;
              const draft: CreatedDraft = {
                object_type: ev.object_type,
                id: ev.id,
                control_ref: ev.control_ref,
                label: ev.label ?? ev.id,
                definition: ev.definition,
                rule: ev.rule,
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, drafts: [...(m.drafts ?? []), draft] } : m,
                ),
              );
            } else if (ev.type === "error") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, streaming: false, error: ev.message ?? "Agent error" }
                    : m,
                ),
              );
            } else if (ev.type === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        streaming: false,
                        content: m.content || ev.text || "",
                      }
                    : m,
                ),
              );
            }
          }
        }

        if (sawDraft) {
          router.refresh();
        }
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, streaming: false, error: err instanceof Error ? err.message : "Stream failed" }
              : m,
          ),
        );
      } finally {
        setStreaming(false);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
        );
      }
    },
    [messages, router, streaming, systemId],
  );

  const ask = React.useCallback(
    (prompt: string) => {
      setOpen(true);
      void sendMessage(prompt);
    },
    [sendMessage],
  );

  function draftHref(d: CreatedDraft): string {
    const { programId } = readRouteContext();
    const at = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("at") : null;
    const q = at ? `?at=${at}` : "";
    if (d.object_type === "implementation" && d.control_ref) {
      return `/programs/${programId}/controls/${d.control_ref}${q}`;
    }
    if (d.object_type === "policy" || d.object_type === "procedure") {
      return `/programs/${programId}/policies${q}`;
    }
    if (d.object_type === "risk") {
      return `/programs/${programId}/risks${q}`;
    }
    if (d.object_type === "query_source" && d.definition) {
      // Nothing is saved: the draft travels in the URL and opens in the query editor.
      const draft = encodeURIComponent(JSON.stringify({ definition: d.definition, rule: d.rule }));
      return `/programs/${programId}/integrations?draft=${draft}${at ? `&at=${at}` : ""}`;
    }
    if (d.object_type === "mapping" && d.control_ref) {
      return `/programs/${programId}/controls/${d.control_ref}${q}`;
    }
    return `/programs/${programId}${q}`;
  }

  const starters = [
    "Summarize the open control gaps and what is blocking each one.",
    "Draft planned implementations for any unimplemented controls on this system.",
    "Draft an Acceptable Use Policy in Markdown linked to our access controls.",
    "Review our open risks and suggest mitigations.",
  ];

  return (
    <AgentContext.Provider value={{ open, setOpen, ask, setSystemId, status }}>
      {children}

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="fixed inset-0 bg-background/60 backdrop-blur-xs"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside
            role="dialog"
            aria-label="OGRL AI Assistant"
            className="relative z-10 flex h-dvh w-[min(96vw,29rem)] flex-col border-l bg-card shadow-2xl"
          >
            <div className="flex items-center justify-between gap-2 border-b px-5 py-3.5">
              <div className="flex min-w-0 items-center gap-2">
                <Sparkles className="size-4 shrink-0 text-agent" aria-hidden />
                <div className="min-w-0">
                  <h2 className="truncate font-display text-lg leading-none">AI Assistant</h2>
                  <p className="mt-1 truncate font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                    {status?.enabled
                      ? status.model?.replace(/^(anthropic|openai):/, "") ?? "connected"
                      : "not configured"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {messages.length > 0 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Clear conversation"
                    title="Clear conversation"
                    disabled={streaming}
                    onClick={() => setMessages([])}
                  >
                    <RotateCcw className="size-3.5" />
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Close AI Assistant"
                  onClick={() => setOpen(false)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            <div className="border-b bg-agent/8 px-5 py-2 text-[11px] text-muted-foreground">
              RFC 0003 §4 guardrails active: drafts only (<span className="font-mono">planned</span> /{" "}
              <span className="font-mono">draft</span> / <span className="font-mono">open</span>). Humans review and
              attest every change.
            </div>

            {status && !status.enabled && (
              <div className="m-4 rounded-xl border border-waived/40 bg-waived-soft p-3.5 text-xs text-waived-ink">
                <div className="font-medium">No LLM API key configured</div>
                <p className="mt-1 opacity-90">{status.hint}</p>
              </div>
            )}

            <div ref={scrollRef} className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
              {messages.length === 0 ? (
                <div className="flex flex-col gap-3 py-4">
                  <p className="text-xs text-muted-foreground">
                    Ask about your program&apos;s computed status, gaps, risks, or have the agent draft implementations
                    and policies directly into OGRL for your review.
                  </p>
                  <div className="flex flex-col gap-2">
                    {starters.map((s) => (
                      <button
                        key={s}
                        type="button"
                        disabled={streaming || status?.enabled === false}
                        onClick={() => void sendMessage(s)}
                        className="rounded-xl border bg-background/50 px-3.5 py-2.5 text-left text-xs text-foreground transition-colors hover:border-agent/50 hover:bg-agent/8 disabled:opacity-50"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m) => (
                  <div
                    key={m.id}
                    className={cn(
                      "flex flex-col gap-2",
                      m.role === "user" ? "items-end" : "items-start",
                    )}
                  >
                    {m.role === "user" ? (
                      <div className="max-w-[88%] rounded-2xl bg-muted px-3.5 py-2 text-sm">
                        {m.content}
                      </div>
                    ) : (
                      <div className="flex w-full flex-col gap-2">
                        {m.tools && m.tools.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {m.tools.map((t, idx) => (
                              <span
                                key={`${t.name}-${idx}`}
                                className="inline-flex items-center gap-1 rounded-full border bg-background/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground"
                              >
                                {t.done ? (
                                  <Check className="size-2.5 text-met" aria-hidden />
                                ) : (
                                  <LoaderCircle className="size-2.5 animate-spin text-agent" aria-hidden />
                                )}
                                <Wrench className="size-2.5 opacity-60" aria-hidden />
                                {t.name}
                              </span>
                            ))}
                          </div>
                        )}

                        {m.error && (
                          <div className="rounded-xl border border-gap/30 bg-gap-soft px-3 py-2 text-xs text-gap-ink">
                            {m.error}
                          </div>
                        )}

                        {(m.content || m.streaming) && (
                          <div className="w-full rounded-2xl border bg-background/40 px-3.5 py-2.5">
                            {m.content && <Markdown>{m.content}</Markdown>}
                            {m.streaming && (
                              <span className="mt-1 inline-block size-2 animate-pulse rounded-full bg-agent align-middle" />
                            )}
                          </div>
                        )}

                        {m.drafts && m.drafts.length > 0 && (
                          <div className="flex flex-col gap-1.5">
                            {m.drafts.map((d) => (
                              <Link
                                key={d.id}
                                href={draftHref(d)}
                                onClick={() => setOpen(false)}
                                className="flex items-center justify-between gap-2 rounded-xl border border-agent/35 bg-agent/8 px-3 py-2 text-xs transition-colors hover:bg-agent/15"
                              >
                                <span className="flex min-w-0 items-center gap-2">
                                  <Sparkles className="size-3.5 shrink-0 text-agent" aria-hidden />
                                  <span className="truncate font-medium">{d.label}</span>
                                </span>
                                <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                              </Link>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void sendMessage(input);
              }}
              className="border-t p-3"
            >
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void sendMessage(input);
                    }
                  }}
                  placeholder={
                    status?.enabled === false
                      ? "Configure ANTHROPIC_API_KEY or OPENAI_API_KEY…"
                      : "Ask OGRL AI to inspect gaps or draft a control/policy…"
                  }
                  disabled={streaming || status?.enabled === false}
                  rows={2}
                  aria-label="Message AI Assistant"
                  className="max-h-32 min-h-10 flex-1 resize-none rounded-xl border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-50"
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={streaming || !input.trim() || status?.enabled === false}
                  aria-label="Send message"
                >
                  {streaming ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
                </Button>
              </div>
            </form>
          </aside>
        </div>
      )}
    </AgentContext.Provider>
  );
}

export function AssistantTriggerButton() {
  const { open, setOpen, status } = useAgent();
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => setOpen(!open)}
      aria-expanded={open}
      className="h-8 gap-1.5 border-agent/35 text-xs hover:border-agent/60 hover:bg-agent/10"
      title={status?.enabled ? `AI Assistant (${status.model})` : "AI Assistant"}
    >
      <Sparkles className="size-3.5 text-agent" aria-hidden />
      <span>AI</span>
    </Button>
  );
}

export function AskAgentButton({
  label,
  prompt,
  size = "xs",
}: {
  label: string;
  prompt: string;
  size?: "xs" | "sm";
}) {
  const { ask } = useAgent();
  return (
    <Button
      type="button"
      variant="outline"
      size={size}
      onClick={() => ask(prompt)}
      className="gap-1.5 border-agent/35 text-xs hover:border-agent/60 hover:bg-agent/10"
    >
      <Sparkles className="size-3 text-agent" aria-hidden />
      <span>{label}</span>
    </Button>
  );
}
