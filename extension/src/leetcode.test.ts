import { describe, expect, it } from "vitest";

import {
  batchMetadataQuery,
  buildCapture,
  checkSubmissionId,
  isAccepted,
  parseBatchMetadata,
  parseCheck,
  parseMemory,
  parseQuestionMetadata,
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

it("reads problem metadata from LeetCode's GraphQL response", () => {
  const body = {
    data: {
      question: {
        questionId: "1827",
        questionFrontendId: "1683",
        title: "Invalid Tweets",
        difficulty: "Easy",
        topicTags: [{ slug: "database" }],
      },
    },
  };
  expect(parseQuestionMetadata(body)).toEqual({
    title: "Invalid Tweets",
    difficulty: "Easy",
    topicTags: ["database"],
    frontendId: "1683",
    questionId: "1827",
  });
  expect(parseQuestionMetadata({ data: { question: null } })).toBeNull();
  expect(parseQuestionMetadata({ data: { question: { difficulty: "Spicy" } } })?.difficulty).toBeNull();

  const submit = { slug: "invalid-tweets", language: "mysql", code: "x", questionId: "1827" };
  const payload = buildCapture(submit, parseCheck("42", CHECK_ACCEPTED)!, "page title", parseQuestionMetadata(body));
  expect(payload).toMatchObject({ title: "Invalid Tweets", difficulty: "Easy", topic_tags: ["database"], frontend_id: "1683" });
});

it("looks up several problems in one GraphQL request", () => {
  const { query, variables } = batchMetadataQuery(["two-sum", "rotting-oranges"]);
  expect(query).toContain("q1: question(titleSlug: $s1)");
  expect(variables).toEqual({ s0: "two-sum", s1: "rotting-oranges" });

  const body = {
    data: {
      q0: { questionId: "1", questionFrontendId: "1", title: "Two Sum", difficulty: "Easy", topicTags: [{ slug: "hash-table" }] },
      q1: null, // a slug LeetCode doesn't know still gets an item, so the server stops asking
    },
  };
  expect(parseBatchMetadata(["two-sum", "gone"], body)).toEqual([
    { slug: "two-sum", title: "Two Sum", difficulty: "Easy", topic_tags: ["hash-table"], frontend_id: "1", question_id: "1" },
    { slug: "gone", title: null, difficulty: null, topic_tags: [], frontend_id: null, question_id: null },
  ]);
});
