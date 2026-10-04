# Honeybon — Product Requirements

Oct 4, 2026 · @Rudransh Vatsa

## Overview

Honeybon captures every solution you submit and returns a four-tier AI review, then shows which techniques you avoid even when they are optimal. It is for people who practice coding problems daily and want to learn from their own code, not generic editorials. It is a deployed, multi-user web app built with React and FastAPI.

**Goals**

- Accepted LeetCode submissions reach Honeybon with no manual step.
- Every review teaches: your code improved, a slightly better approach, the optimal approach, and a competitive programmer's take.
- Analytics surface technique avoidance from your own history, not just weak topics.
- A calm, fast interface you open every day without fatigue.

**Success criteria**

| Criterion | Target |
| --- | --- |
| First review content visible after capture | Within 15 s |
| Full four-tier review complete | Within 60 s on a typical Medium problem |
| Reviews passing schema validation | At least 98%, after at most one repair retry |
| AI technique tags agreeing with LeetCode topic tags | Measured and shown; target set after a baseline |
| Personal use | Opened on at least 5 days a week for a month |

## Core loop

The user solves problems where they already do; Honeybon captures the result, reviews it, and turns the review into long-term insight.

&#91;embedded content: core loop · two entry points, one review pipeline\]

Capture mode decides what happens to a LeetCode submission: Off ignores it, Capture queues it, Analyze reviews it at once. Manual paste and queued items reach the same review worker.

## Scope and phases

Honeybon ships in four phases, and each one ends in a deployed, demoable app. If interviews arrive mid-build, the latest finished phase is the live link.

| Phase | Delivers | Done when |
| --- | --- | --- |
| 1 · Core | GitHub login, manual paste, review pipeline with Claude and Gemini, Review screen with spoiler lock, Library, deployment | A pasted solution gets a validated four-tier review on the live URL |
| 2 · Capture and discuss | Browser extension, three-state capture mode, review queue, Today screen, LeetCode metadata, discussion panel, Groq provider | An accepted LeetCode submission appears reviewed on Today with no manual step |
| 3 · Insight | GitHub repo import, technique analytics, avoidance matrix, weekly insight card | The Insights matrix is populated from imported history on first visit |
| 4 · Later | Spaced re-attempts, personal notes, running AI solutions to verify them | Scoped after Phase 3 |

## Capture

LeetCode submissions arrive through a browser extension; every other platform arrives through manual paste. Both feed the same review pipeline.

**Browser extension (LeetCode)**

- A Chrome Manifest V3 extension runs a content script on LeetCode problem pages.
- It detects an Accepted result by observing the submission-check response, then sends the problem slug, language, code, submission ID, runtime and memory stats where available, and a timestamp.
- Only Accepted submissions are captured in v1.
- It authenticates with a personal access token the user generates in Settings. Tokens are revocable and limited to the capture endpoint.
- The same submission ID is never captured twice. A new accepted submission on a solved problem is stored as a new attempt of that problem.
- After a capture, a small toast on the LeetCode page shows the status and links to the review.
- Failed sends retry with backoff; persistent failures show in the extension popup.

**Capture mode**

| Mode | Behaviour |
| --- | --- |
| Off | Submissions are ignored |
| Capture | Submissions are saved to the review queue, not analyzed |
| Analyze | Submissions are captured and reviewed automatically |

The mode is stored server-side per user. The extension popup and the app sidebar both show and change it, and stay in sync.

**Manual paste**

- Fields: code (required), problem link or statement (one required), platform (detected from the link, editable), language (auto-detected, editable).
- Intended for Codeforces and any other platform.
- Pasted submissions get the same review and appear in the Library and analytics.

## AI review

Every review reviews the user's own code first, then climbs toward the optimal and contest-style solutions. Output is structured JSON so any provider can produce it and analytics can rely on it.

**Review tiers**

| Tier | Content |
| --- | --- |
| Verdict | Correctness, bugs, missed edge cases, inputs that would fail or time out, the user's time and space complexity, technique used vs optimal |
| 1 · Your code, improved | Same approach, tightened; shown as a diff against the original, with line-level comments |
| 2 · Slightly better | A modest step up, with what changes and why it is faster |
| 3 · Optimal | Core insight in plain words, then code, then complexity |
| 4 · CP master | Contest-style tricks and idioms, with a note when the style hurts in interviews |
| Pattern and follow-up | The named pattern and 2–3 related problems |

If the user's solution is already optimal, the review says so and skips to tier 4. Tiers 2–4 sit behind a spoiler lock until the user reveals them.

**Output contract**

- One review schema, defined as a Pydantic model, which every provider must produce.
- The server validates every response. A malformed response gets one repair retry; after that the review is marked failed with a Retry action.
- Technique fields use a fixed taxonomy, never free text: `used_technique` (one value) and `optimal_techniques` (a set, because several can be equally optimal).
- Complexity is stored as display text plus a normalized class, such as `n`, `n log n` or `n^2`, so it can be compared.
- The verdict and tier 1 appear first and later tiers fill in as they finish.

**Technique taxonomy (initial)**

Hashing, two pointers, sliding window, prefix sum, binary search, stack, monotonic stack, linked list, tree DFS, tree BFS, graph DFS, graph BFS, topological sort, union-find, shortest path, heap, greedy, dynamic programming, backtracking, bit manipulation, math, trie, segment tree or Fenwick tree, intervals and sorting, simulation, brute force.

**Providers**

- One adapter interface with two operations: a structured review call and a streaming chat call.
- Adapters for Anthropic, Gemini and Groq, plus a generic OpenAI-compatible adapter for other providers.
- Users bring their own API keys, choose a default model, and can override it per review.
- Each review records provider, model, token counts, latency and estimated cost.

## Discussion panel

Each reviewed problem has a chat panel on the right of its Review screen, so follow-up questions happen next to the code, with full context, through the user's own API key.

- The Discuss button opens and closes the panel. When open, the code and review tiers stack into one column; when closed, they sit side by side.
- One persistent thread per problem, saved and restored on every visit.
- Each thread starts with the problem metadata, the user's code and the structured review as context, so the user never re-explains anything.
- Selecting lines in the code or any tier and choosing "Ask about selection" quotes them into the message box.
- Responses stream in. The user can switch model mid-thread; each message records the model that wrote it.
- When a thread passes a token budget, older turns are summarized before sending. The seeded context is always kept in full.
- Chat requests are rate-limited per user.

## Analytics and import

The avoidance matrix compares the technique each problem needed with the technique the user reached for. Importing past solutions from GitHub fills it on day one.

**Approach-avoidance matrix**

- Rows are the optimal technique, columns the technique used, cells the number of problems. The diagonal means a match.
- Using any technique in a problem's optimal set counts as a match, so BFS on a problem where DFS is equally optimal is not flagged.
- Mismatches split into two kinds: same complexity class (a style choice) and worse complexity class (a real weakness). The worse kind is emphasized.
- Clicking a cell lists the problems behind it.
- Filters: time range, difficulty, platform.
- The AI's optimal techniques are cross-checked against LeetCode's topic tags. Disagreements are marked low-confidence, and the overall disagreement rate is visible.
- The weekly insight card on Today states the single strongest avoidance pattern, and only when it rests on enough problems to be meaningful.

**GitHub import**

- The user connects a repository of past solutions during onboarding or from Settings.
- The importer recognizes LeetHub-style layouts (a folder per problem, named ID plus slug) and matches problems by slug. Folder numbers are LeetCode's internal question IDs, not the visible problem numbers: `1036-rotting-oranges` is problem 994.
- Unmatched folders are listed for manual mapping or skipping, never silently dropped.
- Imports run as background jobs with progress shown.
- Before analysis, the user picks one of: full reviews (cost estimate shown first), a cheap tag-only pass that fills just the technique fields the matrix needs, or no analysis.

## UI and screens

The interface is minimal and calm, in the style of Linear and Raycast, and opens on Today. The approved [mockup](https://claude.ai/artifact/2Q8itrsBcMLtLheFDnznoB) shows the Today and Review screens and is the visual reference.

**Principles**

- Keyboard-first: a ⌘K command palette, j/k to move through lists, Enter to open.
- Dark theme by default, plus light. One blue accent; orange only for things that need attention.
- Geist for interface text, JetBrains Mono for code.
- No confetti, badges or streak resets. Momentum is a seven-day strip that never punishes a missed day.
- Every submission shows a quiet status chip: queued, analyzing, reviewed or failed.
- Diffs use blue and orange rather than green and red, so they read for colour-blind users. Text meets WCAG AA contrast.
- Reading screens work at phone width; capture and editing are desktop-first.

**Screens**

| Screen | Purpose | Key elements |
| --- | --- | --- |
| Today | Home: what needs attention now | Today's submissions with status, review queue with Analyze and Analyze all, one weekly insight card, seven-day strip |
| Review | One problem's full review | Verdict, code with inline comments, tier 1 diff, tiers 2–4 behind Reveal, model picker, Discuss button |
| Discussion panel | Follow-up questions on one problem | Context chips, quoted selections, streaming replies, saved thread |
| Library | Every problem solved | Search, filters by technique, difficulty, platform and "solved suboptimally" |
| Insights | Technique avoidance | Matrix heatmap, drill-down list per cell, confidence markers |
| Paste | Manual review for other platforms | Code, link or statement, platform, language |
| Settings | Account and integrations | Provider keys, default model, capture mode, extension tokens, GitHub import |
| Extension popup | Capture control on LeetCode | Three-state mode, last capture status |

## Architecture and data

The API only accepts work and serves data; every LLM call, import and analysis runs in a background worker, and progress streams back to the browser.

&#91;embedded content: system architecture · 7 components\]

The worker publishes progress to Redis, and the API relays it to the open Review screen over server-sent events, so tiers appear as they finish.

**Tech stack**

| Layer | Choice |
| --- | --- |
| Frontend | React, TypeScript, Vite, TanStack Query, CodeMirror 6 for code views and diffs |
| Styling | Tailwind CSS, with theme colours as CSS variables for dark and light |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic migrations |
| Jobs | Redis with arq or Celery (open question) |
| Database | PostgreSQL |
| Auth | GitHub OAuth with an httpOnly session cookie; hashed personal access tokens for the extension |
| Encryption | Python `cryptography` (Fernet) with a master key from the environment |
| Extension | Chrome Manifest V3, TypeScript |

**Data model**

| Table | Holds |
| --- | --- |
| users | GitHub identity, default model, capture mode |
| provider\_credentials | Encrypted API key per provider, last four characters for display |
| extension\_tokens | Token hash, creation and last-use times, revoked flag |
| problems | Shared metadata: platform, slug, title, difficulty, LeetCode topic tags, link |
| submissions | User, problem, code, language, source (extension, paste or import), status, timestamps |
| reviews | Submission, provider, model, review JSON, used and optimal techniques, complexity classes, tokens, latency, cost |
| chat\_threads | User, problem, running summary of older turns |
| chat\_messages | Thread, role, content, model, quoted selection |
| import\_jobs | Repository, progress, unmatched folders, chosen analysis mode |

## Security, privacy and quality

User API keys and extension tokens are the most sensitive data Honeybon holds, and every query is scoped to one user.

**Security and privacy**

- Provider API keys are encrypted at rest with a server-held master key, decrypted only inside the worker that calls the provider, and never returned to the browser beyond the last four characters.
- Extension tokens are stored only as hashes, limited to the capture endpoint, and revocable.
- Every query on user data filters by user ID; automated tests check that one user can never read another's data.
- User code and problem text are wrapped as data in every prompt, so instructions inside them are not followed.
- Model output is rendered as sanitized Markdown, never raw HTML.
- Review and chat endpoints are rate-limited per user.
- Honeybon stores problem metadata (title, difficulty, tags, link), not LeetCode problem statements.
- Users can export their data and delete their account.

**Non-functional requirements**

- Performance: interface interactions under 100 ms; review timing as in the success criteria.
- Reliability: failed reviews and imports are visible and retryable, never silently lost.
- Observability: structured logs, plus per-review latency, tokens and cost.
- Testing: contract tests run each provider adapter against recorded responses, and the review schema has fixtures for valid and malformed output.
- Accessibility: keyboard reachable throughout, WCAG AA contrast, labelled controls.

## Out of scope and open questions

**Out of scope for v1:** spaced re-attempts, personal notes, running solutions to verify them, browsers other than Chrome, auto-capture on platforms other than LeetCode, teams and sharing, native mobile apps.

**Open questions**

- [ ] Review streaming: one structured call per review, or separate calls for the verdict and tier 1, then tiers 2–4?
- [ ] Repo access: a GitHub OAuth App with repository scope, or a GitHub App installed on a single repository?
- [ ] Job queue: arq (async, fits FastAPI) or Celery (more widely known)?
- [ ] Hosting providers for the frontend, API, worker, Postgres and Redis.
- [ ] Should failed (non-Accepted) submissions ever be capturable?
- [ ] Minimum number of problems before the weekly insight card states a pattern.
- [ ] For LeetCode problems, what does the discussion panel use as the problem statement, given statements are not stored?
