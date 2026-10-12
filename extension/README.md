# Honeybon Capture (Chrome extension)

Sends your **accepted** LeetCode submissions to Honeybon, so reviews show up on Today without
pasting anything.

## Install (developer mode)

```sh
cd extension
npm install
npm run build        # creates dist/
```

1. Open `chrome://extensions` and turn on **Developer mode**.
2. **Load unpacked** → choose `extension/dist`.
3. In Honeybon, go to **Settings → Extension tokens**, create a token and copy it.
4. Click the Honeybon icon in Chrome's toolbar → **Connection settings**, paste the token, **Save**.
   The popup should say "Connected as <your GitHub name>".

After pulling new code, run `npm run build` again and press the reload icon on the extension's
card in `chrome://extensions`.

## How it works

- `src/page-hook.ts` runs inside leetcode.com (MAIN world). It watches LeetCode's own
  `/problems/<slug>/submit/` request and the `/submissions/detail/<id>/check/` results, and
  reads responses only. It never changes requests and never reads cookies.
- When a check comes back **Accepted**, `src/content.ts` passes it to `src/background.ts`, which
  posts it to `<Honeybon address>/api/capture` with your token, then shows a toast on the page.
- Your capture mode (Off / Capture / Analyze) lives on the server, so the popup and the app's
  sidebar always agree. Duplicate submissions are ignored by the server.
- Failed sends (network, a sleeping server, rate limits) are kept and retried after 1, 2, 4, 8
  and 16 minutes; the popup shows what is waiting and has **Retry now**.

- Every 30 minutes the extension asks Honeybon which of your problems still lack LeetCode metadata
  (difficulty, topic tags; mostly GitHub imports) and looks them up from LeetCode's public GraphQL
  API, because LeetCode blocks Honeybon's server. Only public problem metadata is read.

All LeetCode-specific details (URLs, response fields) are in `src/leetcode.ts`, covered by
`npm test`. If LeetCode changes its site, that is the file to update.

## Local development

To capture into a local Honeybon, set **Honeybon address** to `http://localhost:5173` in the
popup and use a token created in your local app.
