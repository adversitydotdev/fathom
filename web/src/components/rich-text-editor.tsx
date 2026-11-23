"use client";

import { Markdown } from "@tiptap/markdown";
import { Placeholder } from "@tiptap/extension-placeholder";
import { TableKit } from "@tiptap/extension-table";
import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Bold, Code2, Italic, Link2, List, ListOrdered, Quote, Redo2, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "cn";

/** Plain-text paste that looks like Markdown is parsed, not inserted literally. */
const MARKDOWN_HINT = /^(#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|>\s|```|\|.*\|)|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)/m;

const STYLES = [
  { value: "p", label: "Normal text" },
  { value: "1", label: "Title" },
  { value: "2", label: "Heading" },
  { value: "3", label: "Subheading" },
] as const;

/**
 * A word-processor style editor that reads and writes Markdown. Toolbar and
 * shortcuts (Ctrl+B, Ctrl+I) for people who don't know Markdown; typed
 * Markdown (`# `, `- `, `**bold**`) and pasted Markdown still convert. The
 * "Markdown" toggle edits the raw source.
 */
export function RichTextEditor({
  id,
  label,
  value,
  onChange,
  placeholder,
  className,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [source, setSource] = useState(false);
  // The last Markdown this editor emitted, so an echo of it is not re-parsed.
  const emitted = useRef(value);
  const editorRef = useRef<Editor | null>(null);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({ underline: false, link: { openOnClick: false, autolink: true } }),
      TableKit,
      Markdown,
      Placeholder.configure({ placeholder: placeholder ?? "Start writing…" }),
    ],
    content: value,
    contentType: "markdown",
    editorProps: {
      attributes: {
        id,
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": label,
        class: "rich-text min-h-40 px-3 py-2.5 text-sm outline-none",
      },
      handlePaste: (_view, event) => {
        const data = event.clipboardData;
        const text = data?.getData("text/plain");
        if (!text || data?.getData("text/html") || !MARKDOWN_HINT.test(text)) return false;
        editorRef.current?.commands.insertContent(text, { contentType: "markdown" });
        return true;
      },
    },
    onUpdate: ({ editor }) => {
      const md = editor.isEmpty ? "" : editor.getMarkdown();
      emitted.current = md;
      onChange(md);
    },
  });
  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // Content arriving later (an existing document loaded after open).
  useEffect(() => {
    if (!editor || value === emitted.current) return;
    emitted.current = value;
    editor.commands.setContent(value, { contentType: "markdown", emitUpdate: false });
  }, [editor, value]);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-input bg-card focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50",
        className,
      )}
    >
      <Toolbar editor={editor} source={source} onSource={setSource} label={label} />
      {source ? (
        <textarea
          aria-label={`${label} (Markdown)`}
          value={value}
          onChange={(e) => {
            emitted.current = e.target.value;
            onChange(e.target.value);
            editor?.commands.setContent(e.target.value, { contentType: "markdown", emitUpdate: false });
          }}
          spellCheck={false}
          className="block min-h-40 w-full resize-y bg-transparent px-3 py-2.5 font-mono text-xs leading-relaxed outline-none"
        />
      ) : (
        <EditorContent editor={editor} className="max-h-[50dvh] overflow-y-auto" />
      )}
    </div>
  );
}

function Toolbar({
  editor,
  source,
  onSource,
  label,
}: {
  editor: Editor | null;
  source: boolean;
  onSource: (v: boolean) => void;
  label: string;
}) {
  const s = useEditorState({
    editor,
    selector: ({ editor: e }) =>
      e && {
        style: e.isActive("heading", { level: 1 }) ? "1" : e.isActive("heading", { level: 2 }) ? "2" : e.isActive("heading", { level: 3 }) ? "3" : "p",
        bold: e.isActive("bold"),
        italic: e.isActive("italic"),
        bullet: e.isActive("bulletList"),
        ordered: e.isActive("orderedList"),
        quote: e.isActive("blockquote"),
        link: e.isActive("link"),
        undo: e.can().undo(),
        redo: e.can().redo(),
      },
  });
  const [linking, setLinking] = useState(false);
  const [href, setHref] = useState("");
  const off = !editor || source;
  const chain = () => editor!.chain().focus();

  const applyLink = () => {
    const url = href.trim();
    if (url) chain().extendMarkRange("link").setLink({ href: /^[a-z]+:|^\/|^#/i.test(url) ? url : `https://${url}` }).run();
    else chain().extendMarkRange("link").unsetLink().run();
    setLinking(false);
  };

  return (
    <div role="toolbar" aria-label={`${label} formatting`} className="border-b bg-muted/30">
      <div className="flex flex-wrap items-center gap-0.5 px-1.5 py-1">
        <select
          aria-label="Text style"
          disabled={off}
          value={s?.style ?? "p"}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "p") chain().setParagraph().run();
            else chain().setHeading({ level: Number(v) as 1 | 2 | 3 }).run();
          }}
          className="h-7 rounded-md bg-transparent px-1.5 text-xs text-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50"
        >
          {STYLES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <Sep />
        <Tool label="Bold (Ctrl+B)" active={s?.bold} disabled={off} onClick={() => chain().toggleBold().run()} icon={Bold} />
        <Tool label="Italic (Ctrl+I)" active={s?.italic} disabled={off} onClick={() => chain().toggleItalic().run()} icon={Italic} />
        <Tool
          label="Link"
          active={s?.link || linking}
          disabled={off}
          onClick={() => {
            setHref(editor?.getAttributes("link").href ?? "");
            setLinking((v) => !v);
          }}
          icon={Link2}
        />
        <Sep />
        <Tool label="Bulleted list" active={s?.bullet} disabled={off} onClick={() => chain().toggleBulletList().run()} icon={List} />
        <Tool label="Numbered list" active={s?.ordered} disabled={off} onClick={() => chain().toggleOrderedList().run()} icon={ListOrdered} />
        <Tool label="Quote" active={s?.quote} disabled={off} onClick={() => chain().toggleBlockquote().run()} icon={Quote} />
        <Sep />
        <Tool label="Undo (Ctrl+Z)" disabled={off || !s?.undo} onClick={() => chain().undo().run()} icon={Undo2} />
        <Tool label="Redo (Ctrl+Shift+Z)" disabled={off || !s?.redo} onClick={() => chain().redo().run()} icon={Redo2} />
        <button
          type="button"
          aria-pressed={source}
          onClick={() => {
            setLinking(false);
            onSource(!source);
          }}
          title={source ? "Back to the formatted editor" : "Edit the Markdown source"}
          className={cn(
            "ml-auto inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground",
            source && "bg-muted text-foreground",
          )}
        >
          <Code2 className="size-3.5" aria-hidden />
          Markdown
        </button>
      </div>
      {linking && !source && (
        <div className="flex items-center gap-1.5 border-t px-2 py-1.5">
          <input
            autoFocus
            aria-label="Link address"
            value={href}
            onChange={(e) => setHref(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                applyLink();
              }
              if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                setLinking(false);
              }
            }}
            placeholder="Paste or type a link"
            className="h-7 min-w-0 flex-1 rounded-md border border-input bg-card px-2 text-xs outline-none focus-visible:border-ring"
          />
          <button type="button" onClick={applyLink} className="h-7 rounded-md bg-primary px-2.5 text-xs font-medium text-primary-foreground">
            Apply
          </button>
          {s?.link && (
            <button
              type="button"
              onClick={() => {
                chain().extendMarkRange("link").unsetLink().run();
                setLinking(false);
              }}
              className="h-7 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted"
            >
              Remove
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Tool({
  label,
  icon: Icon,
  active,
  disabled,
  onClick,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label.replace(/ \(.*\)$/, "")}
      title={label}
      aria-pressed={active ?? undefined}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        "inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
        active && "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
      )}
    >
      <Icon className="size-3.5" />
    </button>
  );
}

function Sep() {
  return <span aria-hidden className="mx-0.5 h-4 w-px bg-border" />;
}
