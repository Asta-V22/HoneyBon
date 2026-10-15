// Runs in the page's own JavaScript world (MAIN) so it can see LeetCode's submit and result-check
// requests. It reads responses only; it never changes requests and never touches cookies.
// Accepted results are handed to the extension's content script with window.postMessage.
// It also pastes a "Verify on LeetCode" solution into the editor, only when the user clicks Paste.

import {
  buildCapture,
  checkSubmissionId,
  isAccepted,
  METADATA_QUERY,
  PAGE_MESSAGE,
  parseQuestionMetadata,
  parseCheck,
  parseSubmitBody,
  parseSubmitResponse,
  submitSlug,
  titleFromDocument,
  type QuestionMetadata,
  type SubmitInfo,
} from "./leetcode";
import { PASTE_MESSAGE, PASTE_RESULT_MESSAGE, sameLanguage, type PasteResult } from "./verify";

const submitted = new Map<string, SubmitInfo>(); // submission ID -> what was submitted
const sent = new Set<string>();

function onSubmit(url: string, requestBody: unknown, responseBody: unknown): void {
  const slug = submitSlug(url);
  if (!slug) return;
  const info = parseSubmitBody(slug, requestBody);
  const id = parseSubmitResponse(responseBody);
  if (info && id) submitted.set(id, info);
}

function onCheck(url: string, responseBody: unknown): void {
  const id = checkSubmissionId(url);
  const info = id ? submitted.get(id) : undefined;
  if (!id || !info || sent.has(id)) return;
  const check = parseCheck(id, responseBody);
  if (!check?.finished) return;
  submitted.delete(id);
  if (!isAccepted(check)) return; // v1 captures accepted submissions only
  sent.add(id);
  void questionMetadata(info.slug).then((metadata) => {
    const payload = buildCapture(info, check, titleFromDocument(document.title), metadata);
    window.postMessage({ type: PAGE_MESSAGE, payload }, window.location.origin);
  });
}

/** Ask LeetCode itself (same origin, the user's own session) for the problem's metadata. */
async function questionMetadata(slug: string): Promise<QuestionMetadata | null> {
  try {
    const response = await originalFetch.call(window, "/graphql/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: METADATA_QUERY, variables: { titleSlug: slug } }),
      signal: AbortSignal.timeout(5000),
    });
    return parseQuestionMetadata(await response.json());
  } catch {
    return null; // capture still goes ahead without it
  }
}

function handle(url: string, requestBody: unknown, responseBody: unknown): void {
  try {
    onSubmit(url, requestBody, responseBody);
    onCheck(url, responseBody);
  } catch {
    // Never let capture problems affect LeetCode itself.
  }
}

// fetch
const originalFetch = window.fetch;
window.fetch = async function (input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await originalFetch.call(this, input, init);
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  if (submitSlug(url) || checkSubmissionId(url)) {
    response
      .clone()
      .json()
      .then((body) => handle(url, init?.body, body))
      .catch(() => {});
  }
  return response;
};

// XMLHttpRequest (some LeetCode builds use it instead of fetch)
const originalOpen = XMLHttpRequest.prototype.open;
const originalSend = XMLHttpRequest.prototype.send;
const urls = new WeakMap<XMLHttpRequest, string>();

XMLHttpRequest.prototype.open = function (this: XMLHttpRequest, ...args: unknown[]) {
  urls.set(this, String(args[1]));
  return (originalOpen as (...a: unknown[]) => void).apply(this, args);
} as typeof XMLHttpRequest.prototype.open;

XMLHttpRequest.prototype.send = function (this: XMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null) {
  const url = urls.get(this) ?? "";
  if (submitSlug(url) || checkSubmissionId(url)) {
    this.addEventListener("load", () => {
      try {
        handle(url, body, JSON.parse(this.responseText));
      } catch {
        // not JSON; ignore
      }
    });
  }
  return originalSend.call(this, body);
};

// ---------------------------------------------------------------- verify on LeetCode: paste

// The slice of Monaco's API used here. LeetCode's editor is Monaco and exposes it as window.monaco.
interface MonacoModel {
  getLanguageId?(): string;
  getModeId?(): string;
  getFullModelRange(): unknown;
  pushEditOperations(before: null[], edits: { range: unknown; text: string }[], cursor: () => null): unknown;
}
interface MonacoEditor {
  getModel(): MonacoModel | null;
  executeEdits(source: string, edits: { range: unknown; text: string; forceMoveMarkers?: boolean }[]): boolean;
  pushUndoStop(): boolean;
  focus(): void;
}
interface Monaco {
  editor: { getEditors?(): MonacoEditor[]; getModels(): MonacoModel[] };
}

const languageOf = (model: MonacoModel) => model.getLanguageId?.() ?? model.getModeId?.() ?? null;
// The solution editor has a real language; the test-case editor is plain text.
const isCode = (model: MonacoModel | null) => !!model && !["plaintext", null].includes(languageOf(model));

/** Replaces the editor's text as one edit, so Ctrl+Z brings the user's own code back. */
function paste(code: string, language: string, force: boolean): PasteResult {
  const monaco = (window as unknown as { monaco?: Monaco }).monaco;
  if (!monaco?.editor) return { ok: false, reason: "no-editor" };
  const editor = monaco.editor.getEditors?.().find((e) => isCode(e.getModel()));
  const model = editor?.getModel() ?? monaco.editor.getModels().find(isCode);
  if (!model) return { ok: false, reason: "no-editor" };
  const editorLanguage = languageOf(model);
  if (!force && sameLanguage(language, editorLanguage) === false) {
    return { ok: false, reason: "language", editorLanguage };
  }
  const edit = { range: model.getFullModelRange(), text: code };
  if (editor) {
    editor.pushUndoStop();
    editor.executeEdits("honeybon", [{ ...edit, forceMoveMarkers: true }]);
    editor.pushUndoStop();
    editor.focus();
  } else {
    model.pushEditOperations([], [edit], () => null);
  }
  return { ok: true, editorLanguage };
}

window.addEventListener("message", (event: MessageEvent) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type !== PASTE_MESSAGE) return;
  const { id, code, language, force } = event.data as { id: string; code: string; language: string; force?: boolean };
  let result: PasteResult;
  try {
    result = typeof code === "string" ? paste(code, String(language), !!force) : { ok: false, reason: "error" };
  } catch {
    result = { ok: false, reason: "error" };
  }
  window.postMessage({ type: PASTE_RESULT_MESSAGE, id, result }, window.location.origin);
});
