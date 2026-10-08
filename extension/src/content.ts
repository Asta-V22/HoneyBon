// Isolated-world content script: relays accepted submissions from the page hook to the
// background worker and shows a small status toast on the LeetCode page.

import { PAGE_MESSAGE, type CapturePayload } from "./leetcode";
import type { CaptureStatus } from "./shared";

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
