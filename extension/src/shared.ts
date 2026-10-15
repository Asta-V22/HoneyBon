// Types and storage shared by the background worker, content script and popup.

import type { CapturePayload } from "./leetcode";
import type { VerifyRequest } from "./verify";

export const DEFAULT_SERVER = "https://honey-bon.vercel.app";
/** Where releases are published; unpacked installs never auto-update, so the popup links here. */
export const RELEASES_API = "https://api.github.com/repos/Asta-V22/HoneyBon/releases?per_page=20";
export const RELEASE_TAG_PREFIX = "ext-v";

export type CaptureMode = "off" | "capture" | "analyze";

export interface Settings {
  serverUrl: string;
  token: string;
}

export interface CaptureStatus {
  at: string;
  slug: string;
  result: "reviewing" | "queued" | "duplicate" | "ignored" | "retrying" | "failed";
  message: string;
  url: string | null;
}

export interface OutboxItem {
  payload: CapturePayload;
  attempts: number;
  nextAt: number; // epoch ms
  lastError: string;
}

export type Message =
  | { type: "capture"; payload: CapturePayload }
  | { type: "state" }
  | { type: "setMode"; mode: CaptureMode }
  | { type: "saveSettings"; settings: Settings }
  | { type: "retryNow" }
  | { type: "verify:set"; request: VerifyRequest }
  | { type: "verify:get"; slug: string }
  | { type: "verify:clear"; slug: string };

export interface UpdateInfo {
  version: string;
  url: string;
}

export interface PopupState {
  settings: Settings;
  update: UpdateInfo | null;
  connected: { login: string; mode: CaptureMode } | null;
  connectionError: string | null;
  last: CaptureStatus | null;
  outbox: OutboxItem[];
}

export async function loadSettings(): Promise<Settings> {
  const { settings } = await chrome.storage.local.get("settings");
  return { serverUrl: DEFAULT_SERVER, token: "", ...(settings as Partial<Settings> | undefined) };
}

export function normalizeServer(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

/** Minutes to wait before retry number `attempts` (1, 2, 4, 8, 16, capped at 30). */
export function backoffMinutes(attempts: number): number {
  return Math.min(30, 2 ** Math.max(0, attempts - 1));
}

export const MAX_ATTEMPTS = 6;

/** -1, 0 or 1 for dotted numeric versions ("0.3.1" vs "0.10.0"); missing parts count as 0. */
export function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map((n) => Number.parseInt(n, 10) || 0);
  const pb = b.split(".").map((n) => Number.parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d) return Math.sign(d);
  }
  return 0;
}

/** The newest published extension release in a GitHub releases list, if any. */
export function latestRelease(body: unknown): UpdateInfo | null {
  if (!Array.isArray(body)) return null;
  let best: UpdateInfo | null = null;
  for (const r of body) {
    const tag = typeof r?.tag_name === "string" ? r.tag_name : "";
    if (!tag.startsWith(RELEASE_TAG_PREFIX) || r.draft || r.prerelease || typeof r.html_url !== "string") continue;
    const version = tag.slice(RELEASE_TAG_PREFIX.length);
    if (!/^\d+(\.\d+)*$/.test(version)) continue;
    if (!best || compareVersions(version, best.version) > 0) best = { version, url: r.html_url };
  }
  return best;
}
