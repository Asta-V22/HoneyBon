# Honeybon Capture (Chrome extension)

Sends your **accepted** LeetCode submissions to Honeybon, so reviews show up on Today without
pasting anything.

## Install from a release

1. Download `honeybon-extension-v<version>.zip` from the
   [latest release](https://github.com/Asta-V22/HoneyBon/releases/latest) and extract it to a
   folder you'll keep.
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick that
   folder.
3. In Honeybon, go to **Settings → Extension tokens**, create a token and copy it.
4. Click the Honeybon icon in Chrome's toolbar → **Connection settings**, paste the token, **Save**.
   The popup should say "Connected as <your GitHub name>".

**Updating.** Unpacked extensions don't update themselves. Once a day the extension checks the
releases and the popup shows "Update available" with a download link. Extract the new zip over the
same folder and press the reload icon on its card in `chrome://extensions`. The same folder keeps
the same extension ID, so the token and settings stay.

## Build from source

```sh
cd extension
npm install
npm run build        # creates dist/ (includes localhost:5173 for local development)
```

Load `extension/dist` unpacked as above. After pulling new code, run `npm run build` again and
press reload on the extension's card.

## Publishing a release

1. Bump `version` in `static/manifest.json` and `package.json` (they must match).
2. Commit, then push a tag: `git tag ext-v0.3.1 && git push origin ext-v0.3.1`.
3. `.github/workflows/extension-release.yml` checks the tag against the manifest, runs the tests,
   builds with `npm run build:release` (no localhost entries) and publishes the zip as a release.

Icons are drawn by `node scripts/make-icons.mjs` into `static/icons/`.

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
- **Verify on LeetCode**: the Review page hands a tier's code to `src/bridge.ts` (a content
  script on the Honeybon app), which the background keeps in session storage for 30 minutes.
  On that problem's LeetCode page, a bar offers **Paste into editor**; the page hook replaces the
  editor's code as one undoable edit (Ctrl+Z restores yours) and warns first if the editor is set
  to another language. Nothing is run or submitted; that stays your click. Details: `src/verify.ts`.

All LeetCode-specific details (URLs, response fields) are in `src/leetcode.ts`, covered by
`npm test`. If LeetCode changes its site, that is the file to update.

## Local development

To capture into a local Honeybon, set **Honeybon address** to `http://localhost:5173` in the
popup and use a token created in your local app.
