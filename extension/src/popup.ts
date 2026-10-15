import { DEFAULT_SERVER, normalizeServer, type CaptureMode, type Message, type PopupState } from "./shared";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const MODES: { id: CaptureMode; label: string; hint: string }[] = [
  { id: "off", label: "Off", hint: "Submissions are ignored." },
  { id: "capture", label: "Capture", hint: "Accepted submissions go to your review queue." },
  { id: "analyze", label: "Analyze", hint: "Accepted submissions are reviewed automatically." },
];

function call(message: Message): Promise<PopupState> {
  return new Promise((resolve, reject) =>
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else if (!response?.ok) reject(new Error(response?.error ?? "Something went wrong."));
      else resolve(response.value as PopupState);
    }),
  );
}

function showError(text: string | null): void {
  const el = $("error");
  el.textContent = text ?? "";
  el.hidden = !text;
}

function render(state: PopupState): void {
  const { connected, connectionError, last, outbox, settings, update } = state;

  const updateLink = $<HTMLAnchorElement>("update");
  updateLink.hidden = !update;
  if (update) {
    updateLink.href = update.url;
    updateLink.textContent = `Update available: v${update.version} · Download`;
  }

  $("status").textContent = connected
    ? `Connected as ${connected.login}`
    : settings.token
      ? connectionError ?? "Not connected"
      : "Add your extension token below to start.";
  $("status-dot").className = `dot ${connected ? "ok" : "off"}`;

  const modes = $("modes");
  modes.replaceChildren(
    ...MODES.map((m) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = m.label;
      button.disabled = !connected;
      button.setAttribute("aria-pressed", String(connected?.mode === m.id));
      button.onclick = () => run({ type: "setMode", mode: m.id });
      return button;
    }),
  );
  $("mode-hint").textContent = connected ? MODES.find((m) => m.id === connected.mode)!.hint : "";

  $("last").textContent = last
    ? `${last.slug}: ${last.message} (${new Date(last.at).toLocaleTimeString()})`
    : "Nothing captured yet.";
  const link = $<HTMLAnchorElement>("last-link");
  link.hidden = !last?.url;
  if (last?.url) link.href = last.url;

  const pending = outbox.length;
  $("outbox").textContent = pending
    ? `${pending} capture${pending === 1 ? "" : "s"} waiting to send: ${outbox[0].lastError}`
    : "";
  $("retry").hidden = !pending;

  if (document.activeElement !== $("server")) $<HTMLInputElement>("server").value = settings.serverUrl;
  $<HTMLInputElement>("token").placeholder = settings.token ? `hb_…${settings.token.slice(-4)} (saved)` : "hb_…";
}

async function run(message: Message): Promise<void> {
  try {
    showError(null);
    render(await call(message));
  } catch (error) {
    showError((error as Error).message);
  }
}

$("settings").addEventListener("submit", async (event) => {
  event.preventDefault();
  const serverUrl = normalizeServer($<HTMLInputElement>("server").value || DEFAULT_SERVER);
  const tokenInput = $<HTMLInputElement>("token");
  const current = (await call({ type: "state" })).settings;
  // A server other than the built-in ones needs the user's permission to be contacted.
  const origin = `${new URL(serverUrl).origin}/*`;
  if (!(await chrome.permissions.contains({ origins: [origin] }))) {
    const granted = await chrome.permissions.request({ origins: [origin] });
    if (!granted) return showError(`Permission to reach ${serverUrl} was not granted.`);
  }
  await run({ type: "saveSettings", settings: { serverUrl, token: tokenInput.value.trim() || current.token } });
  tokenInput.value = "";
});

$("retry").addEventListener("click", () => run({ type: "retryNow" }));

void run({ type: "state" });
