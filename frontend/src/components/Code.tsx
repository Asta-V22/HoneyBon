import { cpp } from "@codemirror/lang-cpp";
import { go } from "@codemirror/lang-go";
import { java } from "@codemirror/lang-java";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { rust } from "@codemirror/lang-rust";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { unifiedMergeView } from "@codemirror/merge";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, lineNumbers } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import { useEffect, useRef } from "react";

function languageExtension(language: string): Extension {
  switch (language) {
    case "cpp":
    case "c":
      return cpp();
    case "python":
    case "python3":
      return python();
    case "java":
    case "kotlin":
    case "csharp":
      return java();
    case "javascript":
      return javascript();
    case "typescript":
      return javascript({ typescript: true });
    case "go":
      return go();
    case "rust":
      return rust();
    default:
      return [];
  }
}

// Calm, theme-aware highlighting: everything reads from the CSS variables in index.css.
const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.modifier, t.operatorKeyword], color: "var(--accent-text)" },
  { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--text-faint)", fontStyle: "italic" },
  { tag: [t.string, t.number, t.bool], color: "var(--text-heading)" },
  { tag: [t.typeName, t.className], color: "var(--text)" , fontWeight: "500" },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "var(--text)" },
]);

const theme = EditorView.theme({
  "&": {
    backgroundColor: "var(--surface)",
    color: "var(--text-secondary)",
    fontSize: "13px",
  },
  ".cm-content": { fontFamily: "var(--font-mono)", padding: "10px 0" },
  ".cm-gutters": {
    backgroundColor: "var(--surface)",
    color: "var(--text-faint)",
    border: "none",
    fontFamily: "var(--font-mono)",
  },
  ".cm-line": { padding: "0 14px 0 6px" },
  "&.cm-focused": { outline: "none" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "var(--selected) !important",
  },
  // Diffs: blue for added, orange for removed, so they read without red/green.
  ".cm-changedLine, .cm-insertedLine": { backgroundColor: "var(--accent-soft) !important" },
  ".cm-changedText, .cm-insertedText": {
    background: "none !important",
    textDecoration: "underline 2px var(--accent)",
  },
  ".cm-deletedChunk": { backgroundColor: "var(--attention-soft) !important" },
  ".cm-deletedChunk .cm-deletedText, .cm-deletedText": {
    background: "none !important",
    textDecoration: "line-through var(--attention)",
  },
  ".cm-changeGutter": { width: "3px" },
  ".cm-changedLineGutter": { backgroundColor: "var(--accent)" },
  ".cm-deletedLineGutter": { backgroundColor: "var(--attention)" },
});

function useEditor(extensions: () => Extension[], doc: string, deps: unknown[]) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const view = new EditorView({
      parent: ref.current,
      state: EditorState.create({
        doc,
        extensions: [
          lineNumbers(),
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
          EditorView.lineWrapping,
          theme,
          syntaxHighlighting(highlight),
          ...extensions(),
        ],
      }),
    });
    return () => view.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}

export function CodeView({ code, language, label }: { code: string; language: string; label: string }) {
  const ref = useEditor(() => [languageExtension(language)], code, [code, language]);
  return <div ref={ref} role="region" aria-label={label} className="overflow-hidden" />;
}

export function DiffView({
  original,
  modified,
  language,
  label,
}: {
  original: string;
  modified: string;
  language: string;
  label: string;
}) {
  const ref = useEditor(
    () => [
      languageExtension(language),
      unifiedMergeView({ original, mergeControls: false, highlightChanges: true, gutter: true }),
    ],
    modified,
    [original, modified, language],
  );
  return <div ref={ref} role="region" aria-label={label} className="overflow-hidden" />;
}
