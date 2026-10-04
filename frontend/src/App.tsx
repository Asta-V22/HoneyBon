import { Navigate, Route, Routes } from "react-router-dom";

import { Sidebar } from "./components/Sidebar";
import { ApiError } from "./lib/api";
import { useMe } from "./lib/hooks";
import { LibraryPage } from "./pages/Library";
import { Login } from "./pages/Login";
import { PastePage } from "./pages/Paste";
import { Placeholder } from "./pages/Placeholder";
import { ReviewPage } from "./pages/Review";
import { SettingsPage } from "./pages/Settings";
import { TodayPage } from "./pages/Today";

export function App() {
  const { data: me, error, isLoading } = useMe();

  if (isLoading) return null;
  if (error instanceof ApiError && error.status === 401) return <Login />;
  if (!me) {
    return <p className="p-10 text-attention-text">Honeybon could not reach its server. Try reloading.</p>;
  }

  return (
    <div className="flex min-h-screen flex-wrap">
      <Sidebar me={me} />
      <main className="min-w-0 flex-[999_1_560px] px-4 pt-9 pb-16 sm:px-10">
        <div className="mx-auto max-w-[1120px]">
          <Routes>
            <Route path="/" element={<Navigate to="/today" replace />} />
            <Route path="/today" element={<TodayPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/insights" element={<Placeholder title="Insights" note="Technique analytics arrive in Phase 3." />} />
            <Route path="/paste" element={<PastePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/review/:submissionId" element={<ReviewPage />} />
            <Route path="*" element={<Placeholder title="Not found" note="That page does not exist." />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
