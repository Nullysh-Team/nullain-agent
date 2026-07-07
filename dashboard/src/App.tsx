import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { BrainPage } from "./pages/Brain";
import { ChatPage } from "./pages/Chat";
import { IntegrationsPage } from "./pages/Integrations";
import { LogsPage } from "./pages/Logs";
import { MemoryPage } from "./pages/Memory";
import { TokensPage } from "./pages/Tokens";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ChatPage />} />
          <Route path="brain" element={<BrainPage />} />
          <Route path="tokens" element={<TokensPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}