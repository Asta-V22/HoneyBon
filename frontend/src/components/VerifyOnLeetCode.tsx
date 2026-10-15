import { useState } from "react";

import { Button } from "./ui";

/**
 * Opens the problem on LeetCode with this code ready to try. With the Honeybon extension, a bar on
 * LeetCode offers to paste it into the editor; without it, the code is copied to the clipboard.
 * Nothing is run or submitted: the user does that on LeetCode.
 */
export function VerifyOnLeetCode({ slug, language, code, label }: { slug: string; language: string; code: string; label: string }) {
  const [note, setNote] = useState<string | null>(null);

  const open = () => {
    // The extension's content script marks the page when it is installed (extension/src/bridge.ts).
    const extension = !!document.documentElement.dataset.honeybonExtension;
    if (extension) {
      window.postMessage({ type: "honeybon:verify", slug, language, code, label }, window.location.origin);
      setNote("Opened LeetCode. Click “Paste into editor” in the Honeybon bar there, then run it yourself.");
    } else {
      navigator.clipboard.writeText(code).then(
        () => setNote("Code copied. Paste it into LeetCode's editor. With the Honeybon extension it's pasted for you."),
        () => setNote("Opened LeetCode. Copy the code above into its editor."),
      );
    }
    // Opened in the click itself, so the browser doesn't treat it as a pop-up.
    window.open(`https://leetcode.com/problems/${slug}/`, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Button onClick={open} title="Open the problem on LeetCode with this code ready to paste">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
        </svg>
        Verify on LeetCode
      </Button>
      {note && (
        <p role="status" className="text-xs text-text-muted">
          {note}
        </p>
      )}
    </div>
  );
}
