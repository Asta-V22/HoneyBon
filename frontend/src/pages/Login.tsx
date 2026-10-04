import { useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";

export function Login() {
  const qc = useQueryClient();
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="flex w-full max-w-sm flex-col gap-6 rounded-xl border border-border bg-surface p-8">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-lg bg-accent font-semibold text-on-accent">
            H
          </div>
          <span className="text-lg font-semibold tracking-tight">Honeybon</span>
        </div>
        <p className="text-text-secondary">
          A four-tier review of every solution you submit, and the techniques you keep avoiding.
        </p>
        <a
          href="/api/auth/github/login"
          className="flex min-h-11 items-center justify-center gap-2 rounded-lg bg-accent font-medium text-on-accent no-underline"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.87-1.37-3.87-1.37-.53-1.33-1.29-1.69-1.29-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.4-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z" />
          </svg>
          Continue with GitHub
        </a>
        {import.meta.env.DEV && (
          <button
            type="button"
            onClick={async () => {
              await api.devLogin();
              await qc.invalidateQueries({ queryKey: ["me"] });
            }}
            className="min-h-10 rounded-lg border border-border-strong bg-raised text-sm text-text-secondary hover:text-text"
          >
            Dev login (local only)
          </button>
        )}
      </div>
    </div>
  );
}
