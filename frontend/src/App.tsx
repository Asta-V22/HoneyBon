import { Navigate, Route, Routes } from "react-router-dom";

import { Sidebar } from "./components/Sidebar";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  return (
    <div className="flex min-h-screen flex-wrap">
      <Sidebar />
      <main className="min-w-0 flex-[999_1_560px] px-5 pt-9 pb-16 sm:px-10">
        <div className="mx-auto max-w-[1120px]">
          <Routes>
            <Route path="/" element={<Navigate to="/today" replace />} />
            <Route path="/today" element={<Placeholder title="Today" />} />
            <Route path="/library" element={<Placeholder title="Library" />} />
            <Route path="/insights" element={<Placeholder title="Insights" />} />
            <Route path="/paste" element={<Placeholder title="Paste code" />} />
            <Route path="/settings" element={<Placeholder title="Settings" />} />
            <Route path="/review/:submissionId" element={<Placeholder title="Review" />} />
            <Route path="*" element={<Placeholder title="Not found" />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
