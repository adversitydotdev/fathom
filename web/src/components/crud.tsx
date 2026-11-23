"use client";

import * as React from "react";
import { Dialog } from "radix-ui";
import { Trash2, X } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import { LoadingButton } from "@/components/spectrumui/loading-button-dependencies";

export function CrudDialog({
  open,
  onOpenChange,
  title,
  description,
  trigger,
  children,
  wide = false,
}: {
  wide?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  trigger?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-background/75 backdrop-blur-xs" />
        <Dialog.Content
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[88dvh] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border bg-card shadow-2xl outline-none",
            wide ? "w-[min(96vw,72rem)]" : "w-[min(94vw,36rem)]",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b px-6 py-4">
            <div className="min-w-0">
              <Dialog.Title className="text-xl font-semibold leading-tight">{title}</Dialog.Title>
              {description && (
                <Dialog.Description className="mt-1 text-xs text-muted-foreground">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Close">
                <X className="size-4" />
              </Button>
            </Dialog.Close>
          </div>
          <div className="overflow-y-auto px-6 py-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Field({
  label,
  hint,
  required,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={htmlFor}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"
      >
        <span>{label}</span>
        {required && <span className="text-gap-ink">*</span>}
      </label>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </div>
  );
}

export function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-card px-2.5 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export function FormError({ error }: { error?: string }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="rounded-xl border border-gap/30 bg-gap-soft px-3 py-2 text-xs text-gap-ink"
    >
      {error}
    </div>
  );
}

export function FormActions({
  pending,
  submitLabel,
  onCancel,
}: {
  pending: boolean;
  submitLabel: string;
  onCancel: () => void;
}) {
  return (
    <div className="flex items-center justify-end gap-2 border-t pt-4">
      <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={pending}>
        Cancel
      </Button>
      <LoadingButton type="submit" size="sm" loading={pending} disabled={pending}>
        {submitLabel}
      </LoadingButton>
    </div>
  );
}

export function RevokeButton({
  onRevoke,
  label = "Revoke",
  compact = false,
}: {
  onRevoke: () => Promise<{ error?: string }>;
  label?: string;
  compact?: boolean;
}) {
  const [confirming, setConfirming] = React.useState(false);
  const [pending, start] = React.useTransition();
  const [error, setError] = React.useState<string>();

  if (!confirming) {
    return (
      <span className="inline-flex items-center gap-1.5">
        {error && <span className="text-xs text-gap-ink">{error}</span>}
        <Button
          type="button"
          variant="ghost"
          size={compact ? "icon-xs" : "xs"}
          className="text-muted-foreground hover:text-gap-ink"
          aria-label={label}
          title={label}
          onClick={(e) => {
            e.stopPropagation();
            setError(undefined);
            setConfirming(true);
          }}
        >
          <Trash2 className="size-3.5" aria-hidden />
          {!compact && <span>{label}</span>}
        </Button>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <LoadingButton
        type="button"
        variant="destructive"
        size="sm"
        className="h-6 px-2 text-xs"
        loading={pending}
        disabled={pending}
        onClick={() =>
          start(async () => {
            const res = await onRevoke();
            if (res.error) {
              setError(res.error);
              setConfirming(false);
            }
          })
        }
      >
        Confirm
      </LoadingButton>
      <Button
        type="button"
        variant="ghost"
        size="xs"
        disabled={pending}
        onClick={() => setConfirming(false)}
      >
        Cancel
      </Button>
    </span>
  );
}
