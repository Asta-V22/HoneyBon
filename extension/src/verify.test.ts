import { describe, expect, it } from "vitest";

import { languageLabel, parseVerifyRequest, problemSlugFromPath, sameLanguage } from "./verify";

describe("verify on LeetCode", () => {
  it("accepts a well-formed request and lower-cases the language", () => {
    expect(parseVerifyRequest({ slug: "two-sum", language: "CPP", code: "int x;", label: " Tier 3 · Optimal " })).toEqual({
      slug: "two-sum",
      language: "cpp",
      code: "int x;",
      label: "Tier 3 · Optimal",
    });
  });

  it("rejects anything malformed", () => {
    expect(parseVerifyRequest(null)).toBeNull();
    expect(parseVerifyRequest({ slug: "../x", language: "cpp", code: "x" })).toBeNull();
    expect(parseVerifyRequest({ slug: "a", language: "c pp", code: "x" })).toBeNull();
    expect(parseVerifyRequest({ slug: "a", language: "cpp", code: "   " })).toBeNull();
    expect(parseVerifyRequest({ slug: "a", language: "cpp", code: "x".repeat(100_001) })).toBeNull();
    expect(parseVerifyRequest({ slug: "a", language: "cpp", code: "x" })?.label).toBe("Honeybon solution");
  });

  it("reads the slug from any problem page path", () => {
    expect(problemSlugFromPath("/problems/two-sum/")).toBe("two-sum");
    expect(problemSlugFromPath("/problems/two-sum/description/")).toBe("two-sum");
    expect(problemSlugFromPath("/problems/two-sum")).toBe("two-sum");
    expect(problemSlugFromPath("/problemset/")).toBeNull();
  });

  it("compares LeetCode languages with Monaco language IDs", () => {
    expect(sameLanguage("python3", "python")).toBe(true);
    expect(sameLanguage("golang", "go")).toBe(true);
    expect(sameLanguage("mysql", "sql")).toBe(true);
    expect(sameLanguage("cpp", "python")).toBe(false);
    expect(sameLanguage("cpp", null)).toBeNull();
    expect(sameLanguage("elixir", "elixir")).toBeNull();
    expect(languageLabel("cpp")).toBe("C++");
    expect(languageLabel("rust")).toBe("Rust");
  });
});
