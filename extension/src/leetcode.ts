// Everything that depends on how leetcode.com works lives here, so a LeetCode change is a
// one-file fix. Pure functions only; covered by leetcode.test.ts.
//
// Flow on leetcode.com: POST /problems/<slug>/submit/ with {lang, question_id, typed_code}
// returns {submission_id}; the page then polls GET /submissions/detail/<id>/v2/check/ until
// state is "SUCCESS", when status_msg says "Accepted" (or the failure reason). Runs use
// /submissions/detail/runcode_<…>/check/ without the version segment and are never captured.

/** window.postMessage type used from the page hook to the content script. */
export const PAGE_MESSAGE = "honeybon:accepted";

export interface SubmitInfo {
  slug: string;
  language: string;
  code: string;
  questionId: string | null;
}

export interface CheckResult {
  submissionId: string;
  finished: boolean;
  status: string; // status_msg, e.g. "Accepted", "Wrong Answer"
  runtimeMs: number | null;
  memoryKb: number | null;
  finishedAt: string | null; // ISO time
}

export interface CapturePayload {
  slug: string;
  submission_id: string;
  status: string;
  language: string;
  code: string;
  runtime_ms: number | null;
  memory_kb: number | null;
  submitted_at: string | null;
  title: string | null;
}

const SUBMIT = /\/problems\/([a-z0-9-]+)\/submit\/?(?:[?#].*)?$/;
// The version segment is optional: submissions moved to /v2/check/ (verified Oct 2026).
const CHECK = /\/submissions\/detail\/(\d+)\/(?:v\d+\/)?check\/?(?:[?#].*)?$/;

export function submitSlug(url: string): string | null {
  return SUBMIT.exec(url)?.[1] ?? null;
}

/** The numeric submission ID of a result check. "Run" checks use runcode_ IDs and never match. */
export function checkSubmissionId(url: string): string | null {
  return CHECK.exec(url)?.[1] ?? null;
}

export function parseSubmitBody(slug: string, body: unknown): SubmitInfo | null {
  const data = asObject(typeof body === "string" ? safeJson(body) : body);
  if (!data || typeof data.typed_code !== "string" || typeof data.lang !== "string") return null;
  return {
    slug,
    language: data.lang,
    code: data.typed_code,
    questionId: data.question_id != null ? String(data.question_id) : null,
  };
}

export function parseSubmitResponse(body: unknown): string | null {
  const id = asObject(body)?.submission_id;
  return typeof id === "number" || (typeof id === "string" && /^\d+$/.test(id)) ? String(id) : null;
}

export function parseCheck(submissionId: string, body: unknown): CheckResult | null {
  const data = asObject(body);
  if (!data) return null;
  const finished = data.state === "SUCCESS" || data.finished === true;
  const finishedMs = typeof data.task_finish_time === "number" ? data.task_finish_time : null;
  return {
    submissionId,
    finished,
    status: typeof data.status_msg === "string" ? data.status_msg : "",
    runtimeMs: parseRuntime(data.status_runtime),
    memoryKb: parseMemory(data.status_memory),
    finishedAt: finishedMs ? new Date(finishedMs).toISOString() : null,
  };
}

export function isAccepted(check: CheckResult): boolean {
  return check.finished && check.status.trim().toLowerCase() === "accepted";
}

/** "3 ms" -> 3 */
export function parseRuntime(value: unknown): number | null {
  const match = typeof value === "string" ? /([\d.]+)\s*ms/i.exec(value) : null;
  return match ? Math.round(Number(match[1])) : null;
}

/** "17.5 MB" -> 17920 (KB) */
export function parseMemory(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = /([\d.]+)\s*(KB|MB|GB)/i.exec(value);
  if (!match) return null;
  const factor = { KB: 1, MB: 1024, GB: 1024 * 1024 }[match[2].toUpperCase() as "KB" | "MB" | "GB"];
  return Math.round(Number(match[1]) * factor);
}

/** "678. Valid Parenthesis String - LeetCode" -> "Valid Parenthesis String" */
export function titleFromDocument(documentTitle: string): string | null {
  const match = /^(?:\d+\.\s*)?(.+?)\s*-\s*LeetCode/.exec(documentTitle);
  return match ? match[1].trim() : null;
}

export function buildCapture(submit: SubmitInfo, check: CheckResult, title: string | null): CapturePayload {
  return {
    slug: submit.slug,
    submission_id: check.submissionId,
    status: check.status,
    language: submit.language,
    code: submit.code,
    runtime_ms: check.runtimeMs,
    memory_kb: check.memoryKb,
    submitted_at: check.finishedAt,
    title,
  };
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;
}
