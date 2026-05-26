import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { getHealth } from "./api/client";
import { Badge, StatusDot } from "./components/ui";
import { FilmIcon, HistoryIcon, PipelineIcon, SparkleIcon } from "./components/icons";
import { GeneratePage } from "./pages/GeneratePage";
import { HistoryPage } from "./pages/HistoryPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { PipelinePage } from "./pages/PipelinePage";
import "./index.css";

const navItems = [
  { to: "/generate", label: "Generate", icon: SparkleIcon },
  { to: "/history", label: "History", icon: HistoryIcon },
];

const routeTitles = [
  { prefix: "/jobs/", title: "Job Detail", eyebrow: "Workspace / jobs" },
  { prefix: "/pipelines/", title: "Pipeline", eyebrow: "Workspace / pipelines" },
  { prefix: "/history", title: "History", eyebrow: "Workspace / history" },
  { prefix: "/generate", title: "Generate", eyebrow: "Workspace / generate" },
];

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/generate" replace />} />
        <Route path="generate" element={<GeneratePage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="jobs/:jobId" element={<JobDetailPage />} />
        <Route path="pipelines/:pipelineId" element={<PipelinePage />} />
        <Route path="*" element={<Navigate to="/generate" replace />} />
      </Route>
    </Routes>
  );
}

function AppShell() {
  const location = useLocation();
  const route = routeTitles.find((item) => location.pathname.startsWith(item.prefix));

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <FilmIcon size={16} />
          </div>
          <div>
            <div className="brand-name">Vertex Studio</div>
            <div className="brand-meta">Creative workspace</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="section-label">Workspace</div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                className={({ isActive }) => `nav-item${isActive ? " nav-item--active" : ""}`}
                key={item.to}
                to={item.to}
              >
                <Icon size={15} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-note">
          <div className="sidebar-note__title">
            <PipelineIcon size={13} />
            Image to video
          </div>
          <p>Turn completed image results into motion from the result view.</p>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div>
            <div className="topbar-eyebrow">{route?.eyebrow ?? "Workspace"}</div>
            <h1>{route?.title ?? "Generate"}</h1>
          </div>
          <HealthIndicator />
        </header>

        <main className="workspace-frame">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function HealthIndicator() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5000,
    retry: false,
  });

  if (health.isLoading) {
    return (
      <Badge>
        <StatusDot tone="pending" />
        Checking API
      </Badge>
    );
  }

  if (health.isError || !health.data?.ok) {
    return (
      <Badge tone="danger">
        <StatusDot tone="danger" />
        API unavailable
      </Badge>
    );
  }

  return (
    <Badge tone="success">
      <StatusDot tone="success" />
      API {health.data.db === "up" ? "connected" : "degraded"}
    </Badge>
  );
}
