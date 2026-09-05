import { chromium } from "@playwright/test";
import react from "@vitejs/plugin-react";
import { createServer } from "vite";
import readline from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";

export const GROUPS = [
  "anonymous_proxy", "user_usage", "generation_ownership", "master_commands",
  "suspension", "logout", "emergency", "mock_recovery",
];
let currentPhase = "startup";

export function validateStart(value) {
  const keys = value && typeof value === "object" ? Object.keys(value).sort() : [];
  if (keys.join(",") !== "backend_url,frontend_origin,secrets,type" || value.type !== "start"
      || value.frontend_origin !== "http://127.0.0.1:18155"
      || !/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(value.backend_url)
      || Object.keys(value.secrets ?? {}).sort().join(",") !== "a,b,master"
      || Object.values(value.secrets).some(secret => typeof secret !== "string" || secret.length < 32)) {
    throw new Error("start_invalid");
  }
  return value;
}

export function validateRecovery(value) {
  if (!value || Object.keys(value).sort().join(",") !== "secrets,type"
      || value.type !== "recovery_done"
      || Object.keys(value.secrets ?? {}).sort().join(",") !== "a,master"
      || Object.values(value.secrets).some(secret => typeof secret !== "string" || secret.length < 32)) {
    throw new Error("recovery_invalid");
  }
  return value;
}

function emit(type, groups, checks, externalRequests) {
  process.stdout.write(`${JSON.stringify({ type, groups, checks, external_requests: externalRequests })}\n`);
}

async function nextMessage(lines, expected) {
  const item = await lines.next();
  if (item.done || item.value.length > 8192) throw new Error("protocol_eof");
  const value = JSON.parse(item.value);
  if (value?.type !== expected) throw new Error("protocol_order");
  return value;
}

async function run() {
  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })[Symbol.asyncIterator]();
  const start = validateStart(await nextMessage(lines, "start"));
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  let vite;
  let browser;
  const contexts = [];
  let externalRequests = 0;
  let checks = 0;
  const ok = (condition, code) => {
    if (!condition) throw new Error(code);
    checks += 1;
  };
  const request = async (page, method, path, body) => page.evaluate(async ({ method, path, body }) => {
    const response = await fetch(path, {
      method,
      cache: "no-store",
      credentials: "same-origin",
      redirect: "manual",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const buffer = await response.arrayBuffer();
    let json = null;
    try { json = JSON.parse(new TextDecoder().decode(buffer)); } catch { /* file response */ }
    return { status: response.status, cache: response.headers.get("cache-control"),
      contentType: response.headers.get("content-type"), length: buffer.byteLength, json };
  }, { method, path, body });
  const contextFor = async secret => {
    const context = await browser.newContext({ baseURL: start.frontend_origin, serviceWorkers: "block" });
    contexts.push(context);
    await context.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.protocol === "http:" && url.hostname === "127.0.0.1" && url.port === "18155") {
        return route.continue();
      }
      externalRequests += 1;
      return route.abort("blockedbyclient");
    });
    if (secret) await context.addCookies([{ name: "creativeops_session", value: secret,
      url: start.frontend_origin, httpOnly: true, sameSite: "Lax", secure: false }]);
    return context;
  };
  try {
    currentPhase = "vite";
    vite = await createServer({
      root, configFile: false, envFile: false, logLevel: "silent", plugins: [react()],
      server: { host: "127.0.0.1", port: 18155, strictPort: true,
        proxy: { "/api": { target: start.backend_url }, "/files": { target: start.backend_url } } },
      define: { "import.meta.env.VITE_API_BASE": JSON.stringify("") },
    });
    await vite.listen();
    browser = await chromium.launch({ headless: true });

    currentPhase = "anonymous_proxy";
    const anon = await contextFor(null);
    const anonPage = await anon.newPage();
    await anonPage.goto("/login");
    ok(await anonPage.getByRole("button", { name: "Google로 계속하기" }).isVisible(), "anonymous_gate_missing");
    ok(!(await anonPage.getByRole("heading", { name: "CreativeOps" }).isVisible().catch(() => false)), "private_ui_visible");
    const loginDisabled = await request(anonPage, "GET", "/api/auth/google/start");
    ok(loginDisabled.status === 503, "login_not_disabled");
    ok(loginDisabled.json?.detail === "login_disabled", "login_error_invalid");
    ok(loginDisabled.cache?.includes("no-store"), "login_cache_unsafe");
    const health = await request(anonPage, "GET", "/api/health");
    ok(health.status === 200, "proxy_health_failed");
    ok(health.json?.ready === true, "backend_not_ready");
    ok(health.json?.vertex?.status === "mock_provider", "provider_not_mock");
    ok(externalRequests === 0, "external_request_seen");

    currentPhase = "user_usage";
    const a = await contextFor(start.secrets.a);
    const b = await contextFor(start.secrets.b);
    const master = await contextFor(start.secrets.master);
    const aPage = await a.newPage();
    const bPage = await b.newPage();
    const masterPage = await master.newPage();
    const profiles = [];
    for (const page of [aPage, bPage, masterPage]) {
      await page.goto("/usage");
      const me = await request(page, "GET", "/api/auth/me");
      ok(me.status === 200, "session_invalid");
      ok(me.cache?.includes("no-store"), "session_cache_unsafe");
      ok(typeof me.json?.id === "string", "identity_missing");
      profiles.push(me.json);
    }
    ok(profiles[0].role === "user" && profiles[1].role === "user", "user_role_invalid");
    ok(profiles[2].role === "master", "master_role_invalid");
    for (const page of [aPage, bPage]) {
      await page.getByRole("heading", { name: "플랜 및 사용량" }).waitFor();
      ok(await page.getByText("Free Plan").first().isVisible(), "free_plan_missing");
      ok(await page.getByText("30일 주기").isVisible(), "cycle_missing");
      const usage = await request(page, "GET", "/api/usage/me");
      ok(usage.status === 200, "usage_failed");
      ok(usage.cache?.includes("private") && usage.cache.includes("no-store"), "usage_cache_unsafe");
      ok(Array.isArray(usage.json?.meters) && usage.json.meters.length === 7, "meters_invalid");
      ok(usage.json?.plan?.current === "free", "usage_plan_invalid");
      ok(usage.json?.cycle?.index >= 0, "cycle_index_invalid");
      ok(usage.json?.concurrency?.limit === 1, "free_limit_invalid");
    }
    ok(!(await aPage.getByRole("link", { name: "관리 콘솔" }).isVisible().catch(() => false)), "master_link_leaked");
    const deniedMaster = await request(aPage, "GET", "/api/master/overview");
    ok(deniedMaster.status === 403, "master_not_denied");
    ok(deniedMaster.cache?.includes("private") && deniedMaster.cache.includes("no-store"), "master_denial_cache_unsafe");

    currentPhase = "generation_ownership";
    const generation = await request(aPage, "POST", "/api/generations", {
      mode: "t2i", model: "imagen-4.0-fast-generate-001", prompt: "mock acceptance image",
      aspect_ratio: "1:1", number_of_images: 1, auto_enhance: false,
    });
    ok(generation.status === 201, "generation_admission_failed");
    ok(generation.json?.state === "pending", "generation_initial_state_invalid");
    const jobId = generation.json.id;
    let job;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      job = await request(aPage, "GET", `/api/generations/${jobId}`);
      if (job.json?.state === "completed") break;
      await new Promise(resolveWait => setTimeout(resolveWait, 100));
    }
    ok(job?.status === 200 && job.json?.state === "completed", "generation_not_completed");
    ok(job.json.assets?.length === 1, "asset_missing");
    const asset = job.json.assets[0];
    ok(asset.mime === "image/png", "asset_mime_invalid");
    const file = await request(aPage, "GET", asset.url);
    ok(file.status === 200 && file.length > 32, "asset_file_invalid");
    ok(file.contentType?.startsWith("image/png"), "asset_content_type_invalid");
    await aPage.goto(`/jobs/${jobId}`);
    await aPage.getByRole("heading", { name: "작업 상세" }).waitFor();
    ok(await aPage.getByText("완료", { exact: true }).first().isVisible(), "detail_state_missing");
    ok(await aPage.getByRole("heading", { name: /이미지 결과.*준비됨/ }).isVisible(), "detail_asset_missing");
    ok(await aPage.locator("img.asset-gallery-card__image").count() === 1, "detail_image_missing");
    const foreignJob = await request(bPage, "GET", `/api/generations/${jobId}`);
    const foreignFile = await request(bPage, "GET", asset.url);
    ok(foreignJob.status === 404, "foreign_job_leaked");
    ok(foreignFile.status === 404, "foreign_file_leaked");
    const charged = await request(aPage, "GET", "/api/usage/me");
    ok(Number(charged.json?.credit?.charged_microcredits) > 0, "charge_missing");
    ok(charged.json?.credit?.held_microcredits === "0", "held_not_released");

    currentPhase = "master_commands";
    await masterPage.goto("/master");
    await masterPage.getByRole("heading", { name: "관리 콘솔" }).waitFor();
    ok(await masterPage.getByRole("link", { name: "관리 콘솔" }).isVisible(), "master_link_missing");
    currentPhase = "suspension";
    await masterPage.getByRole("button", { name: "사용자" }).click();
    await masterPage.getByRole("button", { name: `사용자 관리 ${profiles[0].id}` }).click();
    await masterPage.getByLabel("변경 플랜").selectOption("pro");
    await masterPage.getByText("대상과 변경 내용을 확인했습니다.").click();
    await masterPage.getByRole("button", { name: "변경 적용" }).click();
    await masterPage.getByText("변경이 완료되었습니다. Audit에 기록했습니다.").waitFor();
    ok(true, "plan_command_failed");
    await masterPage.getByRole("button", { name: "닫기" }).click();
    await masterPage.getByRole("button", { name: `사용자 관리 ${profiles[0].id}` }).click();
    await masterPage.getByLabel("조치").selectOption("bonus_grant");
    await masterPage.getByLabel("보너스 크레딧").fill("5");
    await masterPage.getByText("대상과 변경 내용을 확인했습니다.").click();
    await masterPage.getByRole("button", { name: "변경 적용" }).click();
    await masterPage.getByText("변경이 완료되었습니다. Audit에 기록했습니다.").waitFor();
    ok(true, "bonus_command_failed");
    await masterPage.getByRole("button", { name: "닫기" }).click();
    await aPage.goto("/usage");
    await aPage.getByRole("heading", { name: "플랜 및 사용량" }).waitFor();
    ok(await aPage.getByText("Pro Plan").first().isVisible(), "pro_plan_not_visible");
    const afterCommands = await request(aPage, "GET", "/api/usage/me");
    ok(afterCommands.json?.plan?.current === "pro", "pro_plan_not_persisted");
    ok(afterCommands.json?.concurrency?.limit === 3, "pro_limit_invalid");
    ok(Number(afterCommands.json?.credit?.available_microcredits) > Number(charged.json?.credit?.available_microcredits), "bonus_not_visible");
    await masterPage.getByRole("button", { name: "Audit" }).click();
    await masterPage.getByRole("heading", { name: "Audit" }).waitFor();
    ok(await masterPage.getByText("플랜 변경", { exact: true }).count() === 1, "plan_audit_duplicate");
    ok(await masterPage.getByText("보너스 지급", { exact: true }).count() === 1, "bonus_audit_duplicate");

    await masterPage.getByRole("button", { name: "사용자" }).click();
    await masterPage.getByRole("button", { name: `사용자 관리 ${profiles[0].id}` }).click();
    await masterPage.getByLabel("조치").selectOption("suspend");
    await masterPage.getByText("대상과 변경 내용을 확인했습니다.").click();
    await masterPage.getByRole("button", { name: "변경 적용" }).click();
    await masterPage.getByText("변경이 완료되었습니다. Audit에 기록했습니다.").waitFor();
    ok(true, "suspend_command_failed");
    await aPage.reload();
    await aPage.getByRole("button", { name: "Google로 계속하기" }).waitFor();
    ok(!(await aPage.getByRole("heading", { name: "플랜 및 사용량" }).isVisible().catch(() => false)), "suspended_private_ui_visible");
    const suspendedMe = await request(aPage, "GET", "/api/auth/me");
    ok(suspendedMe.status === 401, "suspended_session_accepted");
    ok(suspendedMe.cache?.includes("private") && suspendedMe.cache.includes("no-store"), "suspended_cache_unsafe");
    await masterPage.getByRole("button", { name: "닫기" }).click();
    await masterPage.getByRole("button", { name: `사용자 관리 ${profiles[0].id}` }).click();
    await masterPage.getByLabel("조치").selectOption("reactivate");
    await masterPage.getByText("대상과 변경 내용을 확인했습니다.").click();
    await masterPage.getByRole("button", { name: "변경 적용" }).click();
    await masterPage.getByText("변경이 완료되었습니다. Audit에 기록했습니다.").waitFor();
    ok(true, "reactivate_command_failed");
    const oldAAfterReactivate = await request(aPage, "GET", "/api/auth/me");
    ok(oldAAfterReactivate.status === 401, "old_session_resurrected");

    currentPhase = "logout";
    await bPage.goto("/usage");
    await bPage.getByRole("heading", { name: "플랜 및 사용량" }).waitFor();
    await bPage.getByRole("button", { name: "계정 정보" }).first().click();
    await bPage.getByRole("button", { name: "로그아웃" }).click();
    await bPage.getByRole("button", { name: "Google로 계속하기" }).waitFor();
    ok(!(await bPage.getByRole("heading", { name: "플랜 및 사용량" }).isVisible().catch(() => false)), "logout_private_ui_visible");
    await bPage.goBack();
    ok(await bPage.getByRole("button", { name: "Google로 계속하기" }).isVisible(), "back_restored_private_ui");
    const loggedOut = await request(bPage, "GET", "/api/auth/me");
    ok(loggedOut.status === 401, "logout_session_accepted");
    ok(loggedOut.cache?.includes("private") && loggedOut.cache.includes("no-store"), "logout_cache_unsafe");

    currentPhase = "emergency";
    ok((await request(masterPage, "GET", "/api/auth/me")).status === 200, "master_missing_before_emergency");
    ok(externalRequests === 0, "external_request_seen");
    emit("emergency_ready", 6, checks, externalRequests);
    await nextMessage(lines, "emergency_done");
    await masterPage.reload();
    await masterPage.getByRole("button", { name: "Google로 계속하기" }).waitFor();
    const revokedMaster = await request(masterPage, "GET", "/api/auth/me");
    ok(revokedMaster.status === 401, "emergency_master_not_revoked");
    ok(revokedMaster.cache?.includes("private") && revokedMaster.cache.includes("no-store"), "emergency_cache_unsafe");
    ok(!(await masterPage.getByRole("heading", { name: "관리 콘솔" }).isVisible().catch(() => false)), "emergency_private_ui_visible");
    ok((await request(aPage, "GET", `/api/generations/${jobId}`)).status === 401, "revoked_data_request_accepted");
    ok(externalRequests === 0, "external_request_seen");
    emit("recovery_ready", 7, checks, externalRequests);

    currentPhase = "mock_recovery";
    const recovery = validateRecovery(await nextMessage(lines, "recovery_done"));
    const recoveredA = await contextFor(recovery.secrets.a);
    const recoveredMaster = await contextFor(recovery.secrets.master);
    const recoveredAPage = await recoveredA.newPage();
    const recoveredMasterPage = await recoveredMaster.newPage();
    await recoveredAPage.goto("/usage");
    await recoveredAPage.getByRole("heading", { name: "플랜 및 사용량" }).waitFor();
    ok(await recoveredAPage.getByText("Pro Plan").first().isVisible(), "recovery_plan_lost");
    const recoveredUsage = await request(recoveredAPage, "GET", "/api/usage/me");
    ok(recoveredUsage.status === 200, "recovery_user_failed");
    ok(recoveredUsage.json?.plan?.current === "pro", "recovery_plan_not_persisted");
    ok(Number(recoveredUsage.json?.credit?.charged_microcredits) > 0, "recovery_charge_lost");
    ok((await request(aPage, "GET", "/api/auth/me")).status === 401, "old_a_cookie_recovered");
    await recoveredMasterPage.goto("/master");
    await recoveredMasterPage.getByRole("heading", { name: "관리 콘솔" }).waitFor();
    ok(await recoveredMasterPage.getByRole("link", { name: "관리 콘솔" }).isVisible(), "recovery_master_failed");
    await recoveredMasterPage.getByRole("button", { name: "Audit" }).click();
    ok(await recoveredMasterPage.getByText("플랜 변경", { exact: true }).count() === 1, "recovery_audit_lost");
    ok(await recoveredMasterPage.getByText("보너스 지급", { exact: true }).count() === 1, "recovery_bonus_audit_lost");
    ok((await request(masterPage, "GET", "/api/auth/me")).status === 401, "old_master_cookie_recovered");
    const stillDisabled = await request(recoveredAPage, "GET", "/api/auth/google/start");
    ok(stillDisabled.status === 503 && stillDisabled.json?.detail === "login_disabled", "login_gate_changed");
    ok(stillDisabled.cache?.includes("no-store"), "recovery_login_cache_unsafe");
    ok(externalRequests === 0, "external_request_seen");
    ok(checks >= 80, "insufficient_checks");
    emit("complete", 8, checks, externalRequests);
  } finally {
    await Promise.allSettled(contexts.map(context => context.close()));
    if (browser) await browser.close();
    if (vite) await vite.close();
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  run().catch(error => {
    const known = new Set(["startup", "vite", ...GROUPS]);
    const phase = known.has(currentPhase) ? currentPhase : "browser_step";
    process.stdout.write(`${JSON.stringify({ type: "failed", phase })}\n`);
    process.exitCode = 1;
  });
}
