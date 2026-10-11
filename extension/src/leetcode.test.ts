import { describe, expect, it } from "vitest";

import {
  buildCapture,
  checkSubmissionId,
  isAccepted,
  parseCheck,
  parseMemory,
  parseRuntime,
  parseSubmitBody,
  parseSubmitResponse,
  submitSlug,
  titleFromDocument,
} from "./leetcode";
import { backoffMinutes } from "./shared";

// Shapes of LeetCode's own responses, trimmed to the fields we read.
const CHECK_ACCEPTED = {
  state: "SUCCESS",
  status_code: 10,
  status_msg: "Accepted",
  status_runtime: "3 ms",
  status_memory: "17.5 MB",
  submission_id: "1234567890",
  task_finish_time: 1759900000000,
  finished: true,
};

describe("LeetCode URLs", () => {
  it("recognizes submits, absolute or relative", () => {
    expect(submitSlug("/problems/valid-parenthesis-string/submit/")).toBe("valid-parenthesis-string");
    expect(submitSlug("https://leetcode.com/problems/two-sum/submit/")).toBe("two-sum");
    expect(submitSlug("/problems/two-sum/interpret_solution/")).toBeNull();
  });

  it("recognizes submission checks but not Run checks", () => {
    // The form leetcode.com uses for submissions as of October 2026.
    expect(checkSubmissionId("/submissions/detail/2169310652/v2/check/")).toBe("2169310652");
    expect(checkSubmissionId("https://leetcode.com/submissions/detail/2169310652/v2/check/")).toBe("2169310652");
    expect(checkSubmissionId("/submissions/detail/1234567890/check/")).toBe("1234567890");
    expect(checkSubmissionId("/submissions/detail/runcode_1759_abc/check/")).toBeNull();
  });
});

describe("parsing", () => {
  it("reads the submitted code and language", () => {
    const body = JSON.stringify({ lang: "cpp", question_id: "678", typed_code: "class Solution {};" });
    expect(parseSubmitBody("valid-parenthesis-string", body)).toEqual({
      slug: "valid-parenthesis-string",
      language: "cpp",
      code: "class Solution {};",
      questionId: "678",
    });
    expect(parseSubmitBody("x", "not json")).toBeNull();
  });

  it("reads the submission ID", () => {
    expect(parseSubmitResponse({ submission_id: 1234567890 })).toBe("1234567890");
    expect(parseSubmitResponse({ error: "rate limited" })).toBeNull();
  });

  it("reads a finished, accepted check", () => {
    const check = parseCheck("1234567890", CHECK_ACCEPTED)!;
    expect(isAccepted(check)).toBe(true);
    expect([check.runtimeMs, check.memoryKb]).toEqual([3, 17920]);
    expect(check.finishedAt).toBe(new Date(1759900000000).toISOString());
  });

  it("does not accept pending or failed checks", () => {
    expect(isAccepted(parseCheck("1", { state: "STARTED" })!)).toBe(false);
    expect(isAccepted(parseCheck("1", { ...CHECK_ACCEPTED, status_msg: "Wrong Answer" })!)).toBe(false);
  });

  it("parses runtime, memory and the page title", () => {
    expect(parseRuntime("N/A")).toBeNull();
    expect(parseMemory("512 KB")).toBe(512);
    expect(parseMemory("0B")).toBeNull(); // SQL problems report no memory
    expect(titleFromDocument("678. Valid Parenthesis String - LeetCode")).toBe("Valid Parenthesis String");
    expect(titleFromDocument("LeetCode")).toBeNull();
  });
});

it("builds the capture payload the API expects", () => {
  const submit = { slug: "two-sum", language: "python3", code: "x", questionId: "1" };
  const payload = buildCapture(submit, parseCheck("42", CHECK_ACCEPTED)!, "Two Sum");
  expect(payload).toMatchObject({ slug: "two-sum", submission_id: "42", status: "Accepted", language: "python3" });
});

it("backs off 1, 2, 4, 8, 16, then 30 minutes", () => {
  expect([1, 2, 3, 4, 5, 6, 7].map(backoffMinutes)).toEqual([1, 2, 4, 8, 16, 30, 30]);
});
