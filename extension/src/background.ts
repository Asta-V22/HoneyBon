// Service worker: sends captures to Honeybon with the extension token, retries failures with
// backoff (chrome.alarms survive the worker sleeping), and answers the popup.

import { batchMetadataQuery, parseBatchMetadata, type CapturePayload } from "./leetcode";
import {
  backoffMinutes,
  DEFAULT_SERVER,
  loadSettings,
  MAX_ATTEMPTS,
  normalizeServer,
  type CaptureMode,
  type CaptureStatus,
  type Message,
  type OutboxItem,
  type PopupState,
  latestRelease,
  RELEASES_API,
  compareVersions,
  type UpdateInfo,
} from "./shared";
import { parseVerifyRequest, VERIFY_TTL_MS, type VerifyRequest } from "./verify";

const RETRY_ALARM = "honeybon-retry";
const METADATA_ALARM = "honeybon-metadata";
const METADATA_ROUNDS = 4; // up to 4 x 50 problems per run
const UPDATE_ALARM = "honeybon-update-check";

class PermanentError extends Error {}

async function api(path: string, init: RequestInit = {}): Promise<unknown> {
  const { serverUrl, token } = await loadSettings();
  if (!token) throw new PermanentError("Add your extension token in the Honeybon popup.");
  let response: Response;
  try {
    response = await fetch(`${normalizeServer(serverUrl)}/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init.headers },
    });
  } catch {
    throw new Error("Couldn't reach Honeybon.");
  }
  const body = await response.json().catch(() => ({}));
  if (response.ok) return body;
  const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
  if (response.status === 401) throw new PermanentError("Token rejected. Create a new one in Honeybon Settings.");
  // Rate limits and server or proxy errors (including a sleeping server) are worth retrying.
  if (response.status === 429 || response.status >= 500) throw new Error(detail);
  throw new PermanentError(detail);
}

async function getOutbox(): Promise<OutboxItem[]> {
  return ((await chrome.storage.local.get("outbox")).outbox as OutboxItem[] | undefined) ?? [];
}

async function setOutbox(outbox: OutboxItem[]): Promise<void> {
  await chrome.storage.local.set({ outbox });
  const next = outbox.filter((i) => i.attempts < MAX_ATTEMPTS).map((i) => i.nextAt);
  if (next.length) await chrome.alarms.create(RETRY_ALARM, { when: Math.max(Date.now() + 1000, Math.min(...next)) });
  else await chrome.alarms.clear(RETRY_ALARM);
}

async function record(status: CaptureStatus): Promise<CaptureStatus> {
  await chrome.storage.local.set({ last: status });
  return status;
}

async function send(payload: CapturePayload): Promise<CaptureStatus> {
  const at = new Date().toISOString();
  try {
    const res = (await api("/capture", { method: "POST", body: JSON.stringify(payload) })) as {
      result: CaptureStatus["result"];
      message: string;
      url: string | null;
    };
    return record({ at, slug: payload.slug, result: res.result, message: res.message, url: res.url });
  } catch (error) {
    const message = (error as Error).message;
    if (error instanceof PermanentError) {
      return record({ at, slug: payload.slug, result: "failed", message, url: null });
    }
    const outbox = (await getOutbox()).filter((i) => i.payload.submission_id !== payload.submission_id);
    outbox.push({ payload, attempts: 1, nextAt: Date.now() + backoffMinutes(1) * 60_000, lastError: message });
    await setOutbox(outbox);
    return record({ at, slug: payload.slug, result: "retrying", message: `${message} Will retry.`, url: null });
  }
}

async function flushOutbox(force = false): Promise<void> {
  const remaining: OutboxItem[] = [];
  for (const item of await getOutbox()) {
    if (item.attempts >= MAX_ATTEMPTS || (!force && item.nextAt > Date.now())) {
      remaining.push(item);
      continue;
    }
    try {
      const res = (await api("/capture", { method: "POST", body: JSON.stringify(item.payload) })) as {
        result: CaptureStatus["result"];
        message: string;
        url: string | null;
      };
      await record({ at: new Date().toISOString(), slug: item.payload.slug, ...res });
    } catch (error) {
      if (error instanceof PermanentError) {
        await record({ at: new Date().toISOString(), slug: item.payload.slug, result: "failed", message: (error as Error).message, url: null });
        continue;
      }
      const attempts = item.attempts + 1;
      remaining.push({ ...item, attempts, nextAt: Date.now() + backoffMinutes(attempts) * 60_000, lastError: (error as Error).message });
    }
  }
  await setOutbox(remaining);
}

async function state(): Promise<PopupState> {
  const settings = await loadSettings();
  const { last } = await chrome.storage.local.get("last");
  let connected: PopupState["connected"] = null;
  let connectionError: string | null = null;
  if (settings.token) {
    try {
      const res = (await api("/capture/mode")) as { capture_mode: CaptureMode; github_login: string };
      connected = { login: res.github_login, mode: res.capture_mode };
    } catch (error) {
      connectionError = (error as Error).message;
    }
  }
  return {
    settings,
    update: await availableUpdate(),
    connected,
    connectionError,
    last: (last as CaptureStatus) ?? null,
    outbox: await getOutbox(),
  };
}

async function handle(message: Message, sender: chrome.runtime.MessageSender): Promise<unknown> {
  switch (message.type) {
    case "capture":
      return send(message.payload);
    case "state":
      return state();
    case "setMode":
      await api("/capture/mode", { method: "PUT", body: JSON.stringify({ capture_mode: message.mode }) });
      return state();
    case "saveSettings":
      await chrome.storage.local.set({
        settings: { serverUrl: normalizeServer(message.settings.serverUrl), token: message.settings.token.trim() },
      });
      void backfillMetadata();
      return state();
    case "retryNow":
      await flushOutbox(true);
      return state();
    case "verify:set":
      return setVerify(message.request, sender);
    case "verify:get":
      return getVerify(message.slug, sender);
    case "verify:clear":
      if (fromLeetCode(sender)) await chrome.storage.session.remove(verifyKey(message.slug));
      return null;
  }
}

chrome.runtime.onMessage.addListener((message: Message, sender, sendResponse) => {
  handle(message, sender)
    .then((value) => sendResponse({ ok: true, value }))
    .catch((error: Error) => sendResponse({ ok: false, error: error.message }));
  return true; // respond asynchronously
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RETRY_ALARM) void flushOutbox();
  if (alarm.name === METADATA_ALARM) void backfillMetadata();
  if (alarm.name === UPDATE_ALARM) void checkForUpdate();
});

// ---------------------------------------------------------------- verify on LeetCode

const verifyKey = (slug: string) => `verify:${slug}`;

function senderOrigin(sender: chrome.runtime.MessageSender): string | null {
  try {
    return sender.id === chrome.runtime.id && sender.url ? new URL(sender.url).origin : null;
  } catch {
    return null;
  }
}

const fromLeetCode = (sender: chrome.runtime.MessageSender) => senderOrigin(sender) === "https://leetcode.com";

/** Solutions come only from the Honeybon app, and wait in session storage (cleared with the browser). */
async function setVerify(raw: VerifyRequest, sender: chrome.runtime.MessageSender): Promise<null> {
  const origin = senderOrigin(sender);
  const { serverUrl } = await loadSettings();
  const allowed = new Set([new URL(DEFAULT_SERVER).origin, "http://localhost:5173", safeOrigin(serverUrl)]);
  const request = parseVerifyRequest(raw);
  if (!origin || !allowed.has(origin) || !request) return null;
  await chrome.storage.session.set({ [verifyKey(request.slug)]: { request, at: Date.now() } });
  return null;
}

async function getVerify(slug: string, sender: chrome.runtime.MessageSender): Promise<VerifyRequest | null> {
  if (!fromLeetCode(sender)) return null;
  const key = verifyKey(slug);
  const item = (await chrome.storage.session.get(key))[key] as { request: VerifyRequest; at: number } | undefined;
  if (!item) return null;
  if (Date.now() - item.at > VERIFY_TTL_MS) {
    await chrome.storage.session.remove(key);
    return null;
  }
  return item.request;
}

function safeOrigin(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- metadata backfill

/**
 * Honeybon's server is often blocked by LeetCode, so problems that arrive without metadata (most
 * of all GitHub imports) get their difficulty and topic tags looked up here, from the user's own
 * browser, and sent back. Only public problem metadata is read; never statements or cookies.
 */
async function backfillMetadata(): Promise<void> {
  const { token } = await loadSettings();
  if (!token) return;
  let updated = 0;
  try {
    for (let round = 0; round < METADATA_ROUNDS; round++) {
      const { slugs } = (await api("/capture/metadata/missing")) as { slugs: string[] };
      if (slugs.length === 0) break;
      for (let i = 0; i < slugs.length; i += 10) {
        const chunk = slugs.slice(i, i + 10);
        const response = await fetch("https://leetcode.com/graphql/", {
          method: "POST",
          credentials: "omit",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(batchMetadataQuery(chunk)),
        });
        if (!response.ok) throw new Error(`LeetCode answered ${response.status}`);
        const problems = parseBatchMetadata(chunk, await response.json());
        const res = (await api("/capture/metadata", { method: "POST", body: JSON.stringify({ problems }) })) as {
          updated: number;
        };
        updated += res.updated;
      }
    }
    await chrome.storage.local.set({ metadata: { at: new Date().toISOString(), updated, error: null } });
  } catch (error) {
    await chrome.storage.local.set({
      metadata: { at: new Date().toISOString(), updated, error: (error as Error).message },
    });
  }
}

async function scheduleBackfill(): Promise<void> {
  await chrome.alarms.create(METADATA_ALARM, { delayInMinutes: 1, periodInMinutes: 30 });
  await chrome.alarms.create(UPDATE_ALARM, { delayInMinutes: 2, periodInMinutes: 24 * 60 });
}

// ---------------------------------------------------------------- update check

/**
 * Installs from a GitHub release zip never update themselves, so once a day the extension looks
 * up the newest `ext-v*` release and the popup offers a download link. Failures are ignored.
 */
async function checkForUpdate(): Promise<void> {
  try {
    const response = await fetch(RELEASES_API, { headers: { Accept: "application/vnd.github+json" } });
    if (!response.ok) return;
    const latest = latestRelease(await response.json());
    await chrome.storage.local.set({ latestRelease: latest });
  } catch {
    // offline or rate-limited; try again tomorrow
  }
}

async function availableUpdate(): Promise<UpdateInfo | null> {
  const { latestRelease: latest } = (await chrome.storage.local.get("latestRelease")) as { latestRelease?: UpdateInfo | null };
  return latest && compareVersions(latest.version, chrome.runtime.getManifest().version) > 0 ? latest : null;
}

chrome.runtime.onInstalled.addListener(() => void scheduleBackfill());
chrome.runtime.onStartup.addListener(() => void scheduleBackfill());
