// "Verify on LeetCode": the Honeybon web app hands a solution to the extension, which offers to
// paste it into the LeetCode editor. Nothing is ever run or submitted; the user decides that.
//
// Flow: Review page --window.postMessage--> bridge.ts (content script on Honeybon) --> background
// (chrome.storage.session, per slug) <-- content.ts on leetcode.com/problems/<slug>/, which shows
// a bar; its Paste button asks page-hook.ts (MAIN world) to put the code into LeetCode's editor.
// Pure functions only; covered by verify.test.ts.

/** Web app -> bridge. */
export const VERIFY_MESSAGE = "honeybon:verify";
/** Content script <-> page hook on leetcode.com. */
export const PASTE_MESSAGE = "honeybon:paste";
export const PASTE_RESULT_MESSAGE = "honeybon:paste-result";

/** How long a handed-over solution waits for its LeetCode tab. */
export const VERIFY_TTL_MS = 30 * 60_000;
const MAX_CODE = 100_000;
const SLUG = /^[a-z0-9-]{1,120}$/;
const LANGUAGE = /^[a-z0-9#+]{1,20}$/;

export interface VerifyRequest {
  slug: string;
  language: string; // LeetCode's language slug, e.g. "cpp", "python3"
  code: string;
  label: string; // what the code is, e.g. "Tier 3 · Optimal"
}

export interface PasteResult {
  ok: boolean;
  /** "no-editor" | "language" | "error"; set when ok is false */
  reason?: string;
  editorLanguage?: string | null;
}

export function parseVerifyRequest(data: unknown): VerifyRequest | null {
  if (data === null || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (typeof d.slug !== "string" || !SLUG.test(d.slug)) return null;
  if (typeof d.language !== "string" || !LANGUAGE.test(d.language.toLowerCase())) return null;
  if (typeof d.code !== "string" || !d.code.trim() || d.code.length > MAX_CODE) return null;
  const label = typeof d.label === "string" ? d.label.trim().slice(0, 60) : "";
  return { slug: d.slug, language: d.language.toLowerCase(), code: d.code, label: label || "Honeybon solution" };
}

/** "/problems/two-sum/description/" -> "two-sum" */
export function problemSlugFromPath(path: string): string | null {
  const slug = /^\/problems\/([a-z0-9-]+)(?:\/|$)/.exec(path)?.[1];
  return slug && SLUG.test(slug) ? slug : null;
}

// LeetCode language slug -> the family of Monaco language IDs its editor uses for it.
const FAMILIES: Record<string, string> = {
  cpp: "cpp",
  c: "c",
  java: "java",
  python: "python",
  python3: "python",
  csharp: "csharp",
  javascript: "javascript",
  typescript: "typescript",
  php: "php",
  swift: "swift",
  kotlin: "kotlin",
  dart: "dart",
  golang: "go",
  go: "go",
  ruby: "ruby",
  scala: "scala",
  rust: "rust",
  mysql: "sql",
  mssql: "sql",
  oraclesql: "sql",
  postgresql: "sql",
  sql: "sql",
  pgsql: "sql",
};

const LABELS: Record<string, string> = {
  cpp: "C++",
  c: "C",
  java: "Java",
  python: "Python",
  python3: "Python 3",
  csharp: "C#",
  javascript: "JavaScript",
  typescript: "TypeScript",
  golang: "Go",
  mysql: "MySQL",
  mssql: "MS SQL Server",
  oraclesql: "Oracle",
  postgresql: "PostgreSQL",
};

export function languageLabel(language: string): string {
  return LABELS[language] ?? language.charAt(0).toUpperCase() + language.slice(1);
}

/**
 * Whether the editor is set to the solution's language: true/false, or null when either side is
 * unknown (then the paste goes ahead without asking).
 */
export function sameLanguage(language: string, editorLanguage: string | null | undefined): boolean | null {
  const wanted = FAMILIES[language.toLowerCase()];
  const actual = editorLanguage ? FAMILIES[editorLanguage.toLowerCase()] : undefined;
  if (!wanted || !actual) return null;
  return wanted === actual;
}
