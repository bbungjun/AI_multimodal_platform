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
  { to: "/generate", label: "생성", icon: SparkleIcon },
  { to: "/history", label: "기록", icon: HistoryIcon },
];

const routeTitles = [
  { prefix: "/jobs/", title: "작업 상세", eyebrow: "작업공간 / 작업" },
  { prefix: "/pipelines/", title: "Pipeline", eyebrow: "작업공간 / Pipeline" },
  { prefix: "/history", title: "기록", eyebrow: "작업공간 / 기록" },
  { prefix: "/generate", title: "생성", eyebrow: "작업공간 / 생성" },
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
      <aside className="sidebar" aria-label="주요 내비게이션">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <FilmIcon size={16} />
          </div>
          <div>
            <div className="brand-name">Vertex Studio</div>
            <div className="brand-meta">크리에이티브 작업공간</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="section-label">작업공간</div>
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
            Image to Video
          </div>
          <p>완성된 이미지 결과를 상세 화면에서 영상으로 이어 만들 수 있습니다.</p>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div>
            <div className="topbar-eyebrow">{route?.eyebrow ?? "작업공간"}</div>
            <h1>{route?.title ?? "생성"}</h1>
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
        API 확인 중
      </Badge>
    );
  }

  if (health.isError || !health.data?.ok) {
    return (
      <Badge tone="danger">
        <StatusDot tone="danger" />
        API 연결 불가
      </Badge>
    );
  }

  return (
    <Badge tone="success">
      <StatusDot tone="success" />
      API {health.data.db === "up" ? "연결됨" : "저하됨"}
    </Badge>
  );
}
