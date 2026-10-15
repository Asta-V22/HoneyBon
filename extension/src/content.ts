// Isolated-world content script: relays accepted submissions from the page hook to the
// background worker and shows a small status toast on the LeetCode page. Also shows the
// "Verify on LeetCode" bar when Honeybon handed over a solution for this problem.

import { PAGE_MESSAGE, type CapturePayload } from "./leetcode";
import type { CaptureStatus } from "./shared";
import {
  languageLabel,
  PASTE_MESSAGE,
  PASTE_RESULT_MESSAGE,
  problemSlugFromPath,
  type PasteResult,
  type VerifyRequest,
} from "./verify";

window.addEventListener("message", (event: MessageEvent) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type !== PAGE_MESSAGE) return;
  const payload = event.data.payload as CapturePayload;
  toast({ text: "Sending to Honeybon…", tone: "info" });
  chrome.runtime.sendMessage({ type: "capture", payload }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) {
      toast({ text: "Honeybon extension error. Open its popup for details.", tone: "attention" });
      return;
    }
    const status = response.value as CaptureStatus;
    const tone = status.result === "failed" || status.result === "retrying" ? "attention" : "info";
    toast({ text: status.message, tone, url: status.url ?? undefined });
  });
});

let host: HTMLElement | null = null;
let hideTimer: number | undefined;

function toast({ text, tone, url }: { text: string; tone: "info" | "attention"; url?: string }): void {
  if (!host) {
    host = document.createElement("div");
    host.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483647";
    document.documentElement.appendChild(host);
    host.attachShadow({ mode: "open" });
  }
  const root = host.shadowRoot!;
  const accent = tone === "attention" ? "#f0a45d" : "#8fa8ff";
  root.innerHTML = `
    <style>
      .t{display:flex;align-items:center;gap:10px;max-width:360px;padding:10px 14px;border-radius:10px;
         background:#131518;border:1px solid #2a2e34;color:#e7e8ea;box-shadow:0 8px 24px rgba(0,0,0,.35);
         font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
      .dot{width:7px;height:7px;border-radius:50%;flex:none;background:${accent}}
      a{color:#b3c3ff;white-space:nowrap}
      button{background:none;border:0;color:#8a9099;cursor:pointer;font-size:14px;padding:0 0 0 4px}
    </style>
    <div class="t" role="status"><span class="dot"></span><span class="m"></span></div>`;
  const box = root.querySelector(".t")!;
  root.querySelector(".m")!.textContent = `Honeybon: ${text}`;
  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open review";
    box.appendChild(link);
  }
  const close = document.createElement("button");
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "✕";
  close.onclick = () => {
    host?.remove();
    host = null;
  };
  box.appendChild(close);

  window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(() => {
    host?.remove();
    host = null;
  }, 12_000);
}

// ---------------------------------------------------------------- verify on LeetCode

let bar: HTMLElement | null = null;

async function pendingVerify(slug: string): Promise<VerifyRequest | null> {
  try {
    const response = await chrome.runtime.sendMessage({ type: "verify:get", slug });
    return response?.ok ? (response.value as VerifyRequest | null) : null;
  } catch {
    return null;
  }
}

function askPageToPaste(request: VerifyRequest, force: boolean): Promise<PasteResult> {
  const id = crypto.randomUUID();
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => done({ ok: false, reason: "no-editor" }), 2000);
    function done(result: PasteResult) {
      window.clearTimeout(timer);
      window.removeEventListener("message", onResult);
      resolve(result);
    }
    function onResult(event: MessageEvent) {
      if (event.source !== window || event.data?.type !== PASTE_RESULT_MESSAGE || event.data.id !== id) return;
      done(event.data.result as PasteResult);
    }
    window.addEventListener("message", onResult);
    window.postMessage(
      { type: PASTE_MESSAGE, id, code: request.code, language: request.language, force },
      window.location.origin,
    );
  });
}

type Action = { label: string; primary?: boolean; run: () => void };

function showBar(request: VerifyRequest, text: string, note: string, actions: Action[]): void {
  if (!bar) {
    bar = document.createElement("div");
    bar.style.cssText = "position:fixed;left:20px;bottom:20px;z-index:2147483647";
    document.documentElement.appendChild(bar);
    bar.attachShadow({ mode: "open" });
  }
  const root = bar.shadowRoot!;
  root.innerHTML = `
    <style>
      .b{display:flex;flex-direction:column;gap:8px;max-width:420px;padding:12px 14px;border-radius:10px;
         background:#131518;border:1px solid #2a2e34;color:#e7e8ea;box-shadow:0 8px 24px rgba(0,0,0,.35);
         font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
      .top{display:flex;gap:10px;align-items:flex-start}
      .dot{width:7px;height:7px;margin-top:6px;border-radius:50%;flex:none;background:#8fa8ff}
      .m{flex:1}
      .n{color:#8a9099;font-size:12px;padding-left:17px}
      .row{display:flex;flex-wrap:wrap;gap:6px;padding-left:17px}
      .row:empty{display:none}
      button{font:inherit;font-size:12px;border-radius:7px;padding:4px 10px;cursor:pointer;
             border:1px solid #3a3f47;background:#1d2025;color:#e7e8ea}
      button.p{background:#8fa8ff;border-color:transparent;color:#0d0f12;font-weight:600}
      button.x{border:0;background:none;color:#8a9099;font-size:14px;padding:0 0 0 4px}
    </style>
    <div class="b" role="region" aria-label="Honeybon">
      <div class="top"><span class="dot"></span><span class="m"></span></div>
      <div class="n"></div>
      <div class="row"></div>
    </div>`;
  root.querySelector(".m")!.textContent = `Honeybon: ${text}`;
  root.querySelector(".n")!.textContent = note;
  const row = root.querySelector(".row")!;
  for (const a of actions) {
    const b = document.createElement("button");
    b.textContent = a.label;
    if (a.primary) b.className = "p";
    b.onclick = a.run;
    row.appendChild(b);
  }
  const close = document.createElement("button");
  close.className = "x";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "✕";
  close.onclick = () => {
    bar?.remove();
    bar = null;
    forget(request);
  };
  root.querySelector(".top")!.appendChild(close);
}

function forget(request: VerifyRequest): void {
  chrome.runtime.sendMessage({ type: "verify:clear", slug: request.slug }).catch(() => {});
}

function copyAction(request: VerifyRequest): Action {
  return {
    label: "Copy code",
    run: () => {
      navigator.clipboard.writeText(request.code).then(
        () => toast({ text: "Code copied.", tone: "info" }),
        () => toast({ text: "Couldn't copy. Copy it from the Review page instead.", tone: "attention" }),
      );
    },
  };
}

async function doPaste(request: VerifyRequest, force: boolean): Promise<void> {
  const result = await askPageToPaste(request, force);
  const lang = languageLabel(request.language);
  if (result.ok) {
    showBar(request, `Pasted ${request.label}.`, "Ctrl+Z brings your own code back. Run or submit it when you're ready.", []);
    forget(request);
    return;
  }
  if (result.reason === "language") {
    showBar(
      request,
      `The editor is set to ${languageLabel(result.editorLanguage ?? "?")}, but this solution is ${lang}.`,
      `Switch LeetCode's language to ${lang}, then paste again.`,
      [
        { label: "Paste again", primary: true, run: () => void doPaste(request, false) },
        { label: "Paste anyway", run: () => void doPaste(request, true) },
        copyAction(request),
      ],
    );
    return;
  }
  showBar(request, "Couldn't reach LeetCode's editor.", "Wait for the page to finish loading and try again, or copy the code.", [
    { label: "Try again", primary: true, run: () => void doPaste(request, force) },
    copyAction(request),
  ]);
}

function offer(request: VerifyRequest): void {
  showBar(
    request,
    `${request.label} (${languageLabel(request.language)}) is ready to try.`,
    "Paste replaces the editor's code; Ctrl+Z undoes it. Nothing runs until you click Run or Submit.",
    [{ label: "Paste into editor", primary: true, run: () => void doPaste(request, false) }, copyAction(request)],
  );
}

async function checkForVerify(): Promise<void> {
  const slug = problemSlugFromPath(window.location.pathname);
  if (!slug) return;
  // The Review page hands the solution over as it opens this tab; allow for it arriving late.
  let request = await pendingVerify(slug);
  if (!request) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    request = await pendingVerify(slug);
  }
  if (request) offer(request);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => void checkForVerify(), { once: true });
} else {
  void checkForVerify();
}
