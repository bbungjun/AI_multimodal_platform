import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { getHealth } from "./api/client";
import { Badge, StatusDot } from "./components/ui";
import { CpuIcon, FilmIcon, HistoryIcon, PipelineIcon, SparkleIcon } from "./components/icons";
import { GeneratePage } from "./pages/GeneratePage";
import { HistoryPage } from "./pages/HistoryPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { OpsPage } from "./pages/OpsPage";
import { PipelinePage } from "./pages/PipelinePage";
import { APP_COPY } from "./ui/copy";
import "./index.css";

const navItems = [
  { to: "/generate", label: APP_COPY.nav.generate, icon: SparkleIcon },
  { to: "/history", label: APP_COPY.nav.history, icon: HistoryIcon },
  { to: "/ops", label: APP_COPY.nav.ops, icon: CpuIcon },
];

const routeTitles = [
  { prefix: "/jobs/", ...APP_COPY.routes.jobDetail },
  { prefix: "/pipelines/", ...APP_COPY.routes.pipeline },
  { prefix: "/ops", ...APP_COPY.routes.ops },
  { prefix: "/history", ...APP_COPY.routes.history },
  { prefix: "/generate", ...APP_COPY.routes.generate },
];

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/generate" replace />} />
        <Route path="generate" element={<GeneratePage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="ops" element={<OpsPage />} />
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
    <div className="creative-shell app-shell">
      <aside className="creative-sidebar sidebar" aria-label="주요 내비게이션">
        <NavLink
          aria-label="CreativeOps 홈으로 이동"
          className="creative-brand brand-lockup"
          to="/generate"
        >
          <div className="creative-brand__mark brand-mark" aria-hidden="true">
            <SparkleIcon size={15} />
          </div>
          <div>
            <div className="brand-name">CreativeOps</div>
            <div className="brand-meta">STUDIO · v1.0</div>
          </div>
        </NavLink>

        <nav className="creative-nav sidebar-nav">
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
                {item.to === "/history" && <small>8</small>}
              </NavLink>
            );
          })}
        </nav>

        <nav className="creative-nav creative-nav--system sidebar-nav" aria-label="시스템">
          <div className="section-label">시스템</div>
          <button className="nav-item" type="button">
            <CpuIcon size={15} />
            <span>모델</span>
          </button>
          <button className="nav-item" type="button">
            <PipelineIcon size={15} />
            <span>템플릿</span>
          </button>
          <button className="nav-item" type="button">
            <FilmIcon size={15} />
            <span>설정</span>
          </button>
        </nav>

        <div className="creative-sidebar__footer">
          <div className="creative-system-card">
            <div className="creative-system-card__title">
              <StatusDot tone="success" />
              VERTEX · 정상
            </div>
            <p>4개 엔드포인트 정상</p>
            <p>평균 지연 412ms</p>
          </div>
          <div className="creative-user-card">
            <div className="creative-user-avatar">SK</div>
            <div>
              <strong>S. Kim</strong>
              <span>personal workspace</span>
            </div>
          </div>
        </div>
      </aside>

      <div className="creative-main app-main">
        <header className="creative-topbar topbar">
          <div className="creative-breadcrumb">
            <span>CREATIVEOPS</span>
            <span aria-hidden="true">/</span>
            <strong>{route?.title ?? "생성"}</strong>
          </div>
          <div className="creative-search" aria-hidden="true">
            <SparkleIcon size={13} />
            <span>작업, 프롬프트, asset 검색...</span>
            <kbd>⌘K</kbd>
          </div>
          <div className="creative-topbar__actions">
            <HealthIndicator />
            <button className="creative-icon-button" aria-label="설정" type="button">
              <CpuIcon size={14} />
            </button>
          </div>
        </header>

        <main className="creative-workspace workspace-frame">
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
        {APP_COPY.health.checking}
      </Badge>
    );
  }

  if (health.isError || !health.data?.ok) {
    return (
      <Badge tone="danger">
        <StatusDot tone="danger" />
        {APP_COPY.health.unavailable}
      </Badge>
    );
  }

  return (
    <Badge tone="success">
      <StatusDot tone="success" />
      {health.data.db === "up" ? APP_COPY.health.connected : APP_COPY.health.degraded}
    </Badge>
  );
}
