import type { GenerationMode, JobState } from "../api/client";

export const APP_COPY = {
  brandName: "Vertex Studio",
  brandMeta: "크리에이티브 작업공간",
  nav: {
    generate: "생성",
    history: "기록",
    ops: "운영",
  },
  routes: {
    generate: { title: "생성", eyebrow: "작업공간 / 생성" },
    history: { title: "기록", eyebrow: "작업공간 / 기록" },
    ops: { title: "운영", eyebrow: "작업공간 / 운영" },
    jobDetail: { title: "작업 상세", eyebrow: "작업공간 / 작업" },
    pipeline: { title: "Pipeline", eyebrow: "작업공간 / Pipeline" },
  },
  health: {
    checking: "API 확인 중",
    unavailable: "API 연결 불가",
    connected: "API 연결됨",
    degraded: "API 저하됨",
  },
};

export const MODE_COPY: Record<
  GenerationMode | "pipeline",
  { title: string; short: string; description: string }
> = {
  t2i: {
    title: "텍스트 → 이미지",
    short: "T2I",
    description: "텍스트 프롬프트로 Imagen 이미지 작업을 만듭니다.",
  },
  t2v: {
    title: "텍스트 → 영상",
    short: "T2V",
    description: "텍스트 프롬프트로 Veo 영상 작업을 만듭니다.",
  },
  i2v: {
    title: "이미지 → 영상",
    short: "I2V",
    description: "완성된 이미지 결과에 움직임을 더합니다.",
  },
  pipeline: {
    title: "T2I → I2V Pipeline",
    short: "PIPELINE",
    description: "1단계 이미지 작업과 2단계 I2V 작업을 함께 만듭니다.",
  },
};

export const JOB_STATE_COPY: Record<JobState, string> = {
  pending: "대기 중",
  enhancing: "프롬프트 향상 중",
  queued: "대기열",
  generating: "생성 중",
  polling: "결과 확인 중",
  downloading: "결과 저장 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};

export const ASSET_KIND_COPY = {
  all: "전체 결과 유형",
  image: "이미지",
  video: "영상",
} as const;

export const OPS_COPY = {
  deadLetter: "Dead-letter",
  repair: "Repair",
  recentFailures: "최근 실패 작업",
  outbox: "Outbox",
};
