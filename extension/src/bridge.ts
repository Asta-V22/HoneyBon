// Content script on the Honeybon web app. Tells the page the extension is installed, and passes
// "Verify on LeetCode" solutions from the Review page to the background worker.

import { parseVerifyRequest, VERIFY_MESSAGE } from "./verify";

document.documentElement.dataset.honeybonExtension = chrome.runtime.getManifest().version;

window.addEventListener("message", (event: MessageEvent) => {
  if (event.source !== window || event.origin !== window.location.origin) return;
  if (event.data?.type !== VERIFY_MESSAGE) return;
  const request = parseVerifyRequest(event.data);
  if (request) chrome.runtime.sendMessage({ type: "verify:set", request });
});
