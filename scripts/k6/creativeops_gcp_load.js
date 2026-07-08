import http from "k6/http";
import { check, group, sleep } from "k6";
import exec from "k6/execution";
import { Counter } from "k6/metrics";

const BASE_URL = requiredEnv("BASE_URL").replace(/\/+$/, "");
const PROFILE = (__ENV.PROFILE || "readiness").toLowerCase();
const EXPECTED_VERTEX_STATUS = __ENV.EXPECTED_VERTEX_STATUS || "";
const PROMPT_RATE = positiveNumberEnv("PROMPT_RATE", 3);
const PROMPT_DURATION = __ENV.PROMPT_DURATION || "2m";
const READINESS_MAX_VUS = positiveIntegerEnv("READINESS_MAX_VUS", 10);
const promptEnhanceStatusCodes = new Counter("prompt_enhance_status_codes");

if (!["readiness", "prompt", "mixed"].includes(PROFILE)) {
  throw new Error("PROFILE must be one of: readiness, prompt, mixed.");
}

if ((PROFILE === "prompt" || PROFILE === "mixed") && __ENV.ALLOW_VERTEX_PROMPT !== "1") {
  throw new Error(
    "PROFILE=prompt or mixed performs live prompt-enhancement requests. " +
      "Set ALLOW_VERTEX_PROMPT=1 to acknowledge Vertex cost and quota impact.",
  );
}

export const options = buildOptions();

export default function () {
  if (exec.scenario.name === "prompt_enhancement") {
    promptEnhancement();
    return;
  }

  readiness();
}

function buildOptions() {
  const readinessScenario = {
    executor: "ramping-vus",
    stages: [
      { duration: "30s", target: Math.max(1, Math.floor(READINESS_MAX_VUS / 2)) },
      { duration: "1m", target: READINESS_MAX_VUS },
      { duration: "30s", target: 0 },
    ],
    gracefulRampDown: "10s",
  };

  const promptScenario = {
    executor: "constant-arrival-rate",
    rate: PROMPT_RATE,
    timeUnit: "1m",
    duration: PROMPT_DURATION,
    preAllocatedVUs: positiveIntegerEnv("PROMPT_PREALLOCATED_VUS", 2),
    maxVUs: positiveIntegerEnv("PROMPT_MAX_VUS", 6),
  };

  if (PROFILE === "readiness") {
    return {
      scenarios: { readiness: readinessScenario },
      thresholds: readinessThresholds(),
    };
  }

  if (PROFILE === "prompt") {
    return {
      scenarios: { prompt_enhancement: promptScenario },
      thresholds: promptThresholds(),
    };
  }

  return {
    scenarios: {
      readiness: readinessScenario,
      prompt_enhancement: promptScenario,
    },
    thresholds: promptThresholds(),
  };
}

function readinessThresholds() {
  return {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
  };
}

function promptThresholds() {
  return {
    checks: ["rate>0.95"],
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<30000"],
  };
}

function readiness() {
  group("frontend", () => {
    const response = http.get(`${BASE_URL}/`, {
      tags: { endpoint: "GET /" },
      timeout: "10s",
    });
    check(response, {
      "frontend status is 200": (res) => res.status === 200,
      "frontend returned html": (res) =>
        String(res.headers["Content-Type"] || "").includes("text/html"),
    });
  });

  group("api health", () => {
    const response = http.get(`${BASE_URL}/api/health`, {
      tags: { endpoint: "GET /api/health" },
      timeout: "10s",
    });
    const body = parseJson(response);
    check(response, {
      "health status is 200": (res) => res.status === 200,
      "health ok": () => body.ok === true,
      "health ready": () => body.ready === true,
      "vertex status matches": () =>
        !EXPECTED_VERTEX_STATUS ||
        (body.vertex && body.vertex.status === EXPECTED_VERTEX_STATUS),
    });
  });

  group("ops health", () => {
    const response = http.get(`${BASE_URL}/api/ops/health`, {
      tags: { endpoint: "GET /api/ops/health" },
      timeout: "10s",
    });
    const body = parseJson(response);
    check(response, {
      "ops status is 200": (res) => res.status === 200,
      "ops ok": () => body.ok === true,
      "ops db up": () => body.db === "up",
    });
  });

  sleep(1);
}

function promptEnhancement() {
  const payload = {
    prompt: "a small ceramic cup on a clean wooden desk, soft morning light",
    target_mode: "t2i",
    target_model: "imagen-4.0-fast-generate-001",
    creativity_preset: "faithful",
  };

  const response = http.post(`${BASE_URL}/api/prompts/enhance`, JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    tags: { endpoint: "POST /api/prompts/enhance" },
    timeout: "120s",
  });
  const body = parseJson(response);
  promptEnhanceStatusCodes.add(1, { status: String(response.status) });

  if (response.status !== 201) {
    console.warn(`prompt enhance returned HTTP ${response.status}`);
  }

  check(response, {
    "prompt enhance status is 201": (res) => res.status === 201,
    "prompt enhance returned id": () => typeof body.id === "string" && body.id.length > 0,
    "prompt enhance returned text": () =>
      typeof body.enhanced === "string" && body.enhanced.trim().length > 0,
  });
}

function parseJson(response) {
  try {
    return response.json();
  } catch (_) {
    return {};
  }
}

function requiredEnv(name) {
  const value = __ENV[name];
  if (!value) {
    throw new Error(`${name} is required.`);
  }
  return value;
}

function positiveNumberEnv(name, fallback) {
  const raw = __ENV[name];
  if (raw === undefined || raw === "") {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${name} must be a positive number.`);
  }
  return value;
}

function positiveIntegerEnv(name, fallback) {
  const value = positiveNumberEnv(name, fallback);
  if (!Number.isInteger(value)) {
    throw new Error(`${name} must be a positive integer.`);
  }
  return value;
}
