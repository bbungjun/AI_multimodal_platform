import type { GenerationMode, JobState } from "../api/client";

export const AUTH_COPY = {
  title: "작업공간에 로그인", description: "Google 계정으로 CreativeOps 작업공간을 시작하세요.",
  continueGoogle: "Google로 계속하기", checking: "로그인 상태 확인 중", signingOut: "로그아웃 확인 중",
  unavailable: "로그인 상태를 확인할 수 없습니다.", unconfirmed: "로그아웃 완료를 확인할 수 없습니다.",
  expired: "로그인이 만료되었거나 종료되었습니다. 다시 로그인해 주세요.",
  signedOut: "로그아웃되었습니다.", loginError: "로그인을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  retry: "다시 확인", retryLogout: "로그아웃 다시 시도", logout: "로그아웃", account: "계정 정보",
  configurationError: "API 주소 설정을 확인해 주세요. 같은 origin의 root 주소 또는 빈 VITE_API_BASE만 지원합니다.",
  noDraft: "입력 중인 내용은 자동 저장되지 않습니다. 로그인 이동·만료·계정 전환 시 초기화됩니다.",
};

export const APP_COPY = {
  brandName: "Vertex Studio",
  brandMeta: "크리에이티브 작업공간",
  nav: {
    generate: "생성",
    history: "기록",
    usage: "사용량",
    ops: "운영",
  },
  routes: {
    generate: { title: "생성", eyebrow: "작업공간 / 생성" },
    history: { title: "기록", eyebrow: "작업공간 / 기록" },
    usage: { title: "사용량", eyebrow: "작업공간 / 사용량" },
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

export const USAGE_COPY = {
  title: "플랜 및 사용량",
  description: "현재 30일 주기의 크레딧, 동시 처리 한도와 과금 meter를 확인합니다.",
  loading: "사용량을 불러오는 중입니다.",
  busy: "사용량 정산이 진행 중입니다. 잠시 후 다시 시도해 주세요.",
  unavailable: "현재 사용량을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  invalid: "사용량 응답을 안전하게 표시할 수 없습니다.",
  retry: "다시 시도",
  refresh: "사용량 새로고침",
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
