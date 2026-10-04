// Typed client for the Honeybon API. Same-origin (/api), so the httpOnly session cookie rides along.

export type CaptureMode = "off" | "capture" | "analyze";
export type SubmissionStatus = "queued" | "analyzing" | "reviewed" | "failed";

export interface ProviderKey {
  provider: string;
  last_four: string;
  base_url: string | null;
}

export interface Me {
  id: string;
  github_login: string;
  avatar_url: string | null;
  default_provider: string | null;
  default_model: string | null;
  capture_mode: CaptureMode;
  providers: ProviderKey[];
  available_providers: string[];
  provider_models: Record<string, string[]>;
}

export interface Problem {
  id: string;
  platform: string;
  slug: string;
  title: string | null;
  difficulty: string | null;
  topic_tags: string[];
  url: string | null;
}

export interface Complexity {
  display: string;
  normalized: string;
}

export interface ReviewJson {
  verdict: {
    correct: boolean;
    summary: string;
    bugs: string[];
    missed_edge_cases: string[];
    failing_inputs: { input: string; outcome: string; reason: string }[];
    time: Complexity;
    space: Complexity;
    used_technique: string;
    optimal_techniques: string[];
    optimal_time: Complexity;
    /** Absent on reviews made before space was part of optimality. */
    optimal_space?: Complexity;
    is_optimal: boolean;
  };
  tier1: { summary: string; code: string; line_comments: { line: number; comment: string }[] };
  tier2?: {
    approach: string;
    what_changes: string;
    why_faster: string;
    code: string;
    time: Complexity;
    space: Complexity;
  } | null;
  tier3?: { insight: string; code: string; time: Complexity; space: Complexity } | null;
  tier4?: { notes: string; code: string; interview_caveat: string | null };
  pattern?: { name: string; related_problems: { title: string; platform: string; slug: string | null }[] };
}

export interface Review {
  id: string;
  provider: string;
  model: string;
  served_model: string | null;
  review_json: ReviewJson | null;
  error: string | null;
  used_technique: string | null;
  optimal_techniques: string[];
  time_class: string | null;
  space_class: string | null;
  optimal_time_class: string | null;
  optimal_space_class: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  cost_usd: string | null;
  repair_attempted: boolean;
  created_at: string;
  completed_at: string | null;
}

export interface Submission {
  id: string;
  problem: Problem;
  code: string;
  statement: string | null;
  language: string;
  source: "extension" | "paste" | "import";
  status: SubmissionStatus;
  created_at: string;
  review: Review | null;
}

export interface SubmissionListItem {
  id: string;
  problem: Problem;
  language: string;
  source: Submission["source"];
  status: SubmissionStatus;
  created_at: string;
  review: {
    used_technique: string | null;
    optimal_techniques: string[];
    time_class: string | null;
    space_class: string | null;
    optimal_time_class: string | null;
    optimal_space_class: string | null;
  } | null;
}

export interface SubmissionPage {
  items: SubmissionListItem[];
  total: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "failed";
  error: string | null;
  provider: string | null;
  model: string | null;
  quoted_selection: string | null;
  created_at: string;
}

export interface ChatThread {
  thread_id: string | null;
  summarized_messages: number;
  messages: ChatMessage[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join("; ")
            : message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  me: () => request<Me>("GET", "/me"),
  updateMe: (body: Partial<Pick<Me, "default_provider" | "default_model" | "capture_mode">>) =>
    request<Me>("PATCH", "/me", body),
  saveKey: (provider: string, api_key: string, base_url?: string) =>
    request<Me>("PUT", `/me/providers/${provider}`, { api_key, base_url: base_url || null }),
  deleteKey: (provider: string) => request<Me>("DELETE", `/me/providers/${provider}`),
  deleteAccount: () => request<void>("DELETE", "/me"),
  devLogin: () => request<void>("POST", "/auth/dev-login"),
  logout: () => request<void>("POST", "/auth/logout"),

  paste: (body: {
    code: string;
    link?: string;
    statement?: string;
    platform?: string;
    language?: string;
    title?: string;
  }) => request<Submission>("POST", "/submissions", body),
  submissions: (params: Record<string, string | boolean | number | undefined>) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== false) qs.set(k, String(v));
    return request<SubmissionPage>("GET", `/submissions?${qs}`);
  },
  submission: (id: string) => request<Submission>("GET", `/submissions/${id}`),
  requestReview: (id: string, body: { provider?: string; model?: string }) =>
    request<Submission>("POST", `/submissions/${id}/reviews`, body),
  thread: (submissionId: string) => request<ChatThread>("GET", `/submissions/${submissionId}/chat`),
  sendChat: (
    submissionId: string,
    body: { content: string; quoted_selection?: string; provider?: string; model?: string },
  ) => request<ChatThread>("POST", `/submissions/${submissionId}/chat`, body),
};

export const TECHNIQUES = [
  "hashing", "two_pointers", "sliding_window", "prefix_sum", "binary_search", "stack",
  "monotonic_stack", "linked_list", "tree_dfs", "tree_bfs", "graph_dfs", "graph_bfs",
  "topological_sort", "union_find", "shortest_path", "heap", "greedy", "dynamic_programming",
  "backtracking", "bit_manipulation", "math", "trie", "segment_or_fenwick_tree",
  "intervals_and_sorting", "simulation", "brute_force",
] as const;

const TECHNIQUE_LABELS: Record<string, string> = {
  dynamic_programming: "DP",
  graph_bfs: "BFS",
  graph_dfs: "DFS",
  tree_bfs: "Tree BFS",
  tree_dfs: "Tree DFS",
  segment_or_fenwick_tree: "Segment / Fenwick tree",
  intervals_and_sorting: "Intervals & sorting",
};

export function techniqueLabel(t: string): string {
  if (TECHNIQUE_LABELS[t]) return TECHNIQUE_LABELS[t];
  const s = t.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const PROVIDER_LABELS: Record<string, string> = { anthropic: "Anthropic", gemini: "Gemini", groq: "Groq" };
