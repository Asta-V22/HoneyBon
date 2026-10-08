// Runs in the page's own JavaScript world (MAIN) so it can see LeetCode's submit and result-check
// requests. It reads responses only; it never changes requests and never touches cookies.
// Accepted results are handed to the extension's content script with window.postMessage.

import {
  buildCapture,
  checkSubmissionId,
  isAccepted,
  PAGE_MESSAGE,
  parseCheck,
  parseSubmitBody,
  parseSubmitResponse,
  submitSlug,
  titleFromDocument,
  type SubmitInfo,
} from "./leetcode";

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
  const payload = buildCapture(info, check, titleFromDocument(document.title));
  window.postMessage({ type: PAGE_MESSAGE, payload }, window.location.origin);
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
