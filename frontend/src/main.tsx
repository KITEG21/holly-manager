import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { Role } from "./api";
import { AuthProvider, homeFor, RequireRole, useAuth } from "./auth";
import { AppShell } from "./components/Shell";
import { ToastProvider } from "./components/ui";
import "./index.css";
import Admin from "./pages/Admin";
import Chat from "./pages/Chat";
import Escalations from "./pages/Escalations";
import LeadInternal from "./pages/LeadInternal";
import Leads from "./pages/Leads";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/team/Dashboard";
import MyTasks from "./pages/team/MyTasks";
import Project from "./pages/team/Project";
import Projects from "./pages/team/Projects";
import Reports from "./pages/team/Reports";
import Timesheet from "./pages/team/Timesheet";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

function team(roles: Role[], page: ReactNode) {
  return (
    <RequireRole roles={roles}>
      <AppShell>{page}</AppShell>
    </RequireRole>
  );
}

const TEAM: Role[] = ["developer", "admin"];
const ADMIN: Role[] = ["admin"];

function Home() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />

              {/* Cliente: solo su chat. El admin puede abrir el de cualquier cliente. */}
              <Route path="/chat" element={<RequireRole roles={["client"]}><Chat /></RequireRole>} />
              <Route path="/chat/:leadId" element={<RequireRole roles={ADMIN}><Chat /></RequireRole>} />

              <Route path="/dev" element={team(TEAM, <Dashboard />)} />
              <Route path="/dev/tasks" element={team(TEAM, <MyTasks />)} />
              <Route path="/dev/projects" element={team(TEAM, <Projects />)} />
              <Route path="/dev/projects/:leadId" element={team(TEAM, <Project />)} />
              <Route path="/dev/timesheet" element={team(TEAM, <Timesheet />)} />
              <Route path="/dev/reports" element={team(TEAM, <Reports />)} />

              <Route path="/admin/leads" element={team(ADMIN, <Leads />)} />
              <Route path="/admin/leads/:leadId" element={team(ADMIN, <LeadInternal />)} />
              <Route path="/admin/escalations" element={team(ADMIN, <Escalations />)} />
              <Route path="/admin/config" element={team(ADMIN, <Admin />)} />

              <Route path="*" element={<Home />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
