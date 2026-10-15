// Types and storage shared by the background worker, content script and popup.

import type { CapturePayload } from "./leetcode";
import type { VerifyRequest } from "./verify";

export const DEFAULT_SERVER = "https://honey-bon.vercel.app";

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

export interface PopupState {
  settings: Settings;
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
