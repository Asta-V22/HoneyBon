import { describe, expect, it } from "vitest";

import { compareVersions, latestRelease } from "./shared";

describe("update check", () => {
  it("compares dotted versions numerically", () => {
    expect(compareVersions("0.3.1", "0.3.0")).toBe(1);
    expect(compareVersions("0.10.0", "0.9.9")).toBe(1);
    expect(compareVersions("0.3", "0.3.0")).toBe(0);
    expect(compareVersions("0.3.0", "1.0.0")).toBe(-1);
  });

  it("picks the newest published extension release", () => {
    const release = (tag: string, extra = {}) => ({ tag_name: tag, html_url: `https://x/${tag}`, draft: false, prerelease: false, ...extra });
    expect(
      latestRelease([
        release("ext-v0.3.1"),
        release("ext-v0.10.0"),
        release("ext-v0.11.0", { draft: true }),
        release("ext-v0.12.0", { prerelease: true }),
        release("v2.0.0"),
        release("ext-vnext"),
      ]),
    ).toEqual({ version: "0.10.0", url: "https://x/ext-v0.10.0" });
    expect(latestRelease([])).toBeNull();
    expect(latestRelease({ message: "rate limited" })).toBeNull();
  });
});
