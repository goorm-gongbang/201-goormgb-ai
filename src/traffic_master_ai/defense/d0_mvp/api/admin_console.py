"""Read-only admin console API for near-real-time defense monitoring."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from .compat import APIRouter, HTMLResponse, Header, HTTPException
from .http_errors import ensure_route_handler_alias
from .runtime import DefenseRuntime

_ADMIN_ROLES = {"admin_readonly", "admin_operator"}
_ADMIN_SHARED_TOKEN_ENV = "TM_ADMIN_SHARED_TOKEN"
_ADMIN_ROLE_TOKEN_ENVS = {
    "admin_readonly": "TM_ADMIN_READONLY_TOKEN",
    "admin_operator": "TM_ADMIN_OPERATOR_TOKEN",
}


def create_admin_console_router(runtime: Optional[DefenseRuntime] = None) -> APIRouter:
    rt = runtime or DefenseRuntime()
    router = APIRouter(prefix="/admin/defense", tags=["defense-admin"])

    def _require_access(role: Optional[str], token: Optional[str]) -> None:
        role_value = role if isinstance(role, str) else None
        token_value = token if isinstance(token, str) else None
        if role_value not in _ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="admin role required")
        configured_tokens = _configured_tokens_for_role(role_value)
        if not configured_tokens:
            raise HTTPException(status_code=503, detail="admin access control misconfigured")
        if not token_value:
            raise HTTPException(status_code=403, detail="admin token required")
        if not any(secrets.compare_digest(token_value, candidate) for candidate in configured_tokens):
            raise HTTPException(status_code=403, detail="invalid admin token")

    @router.get("/ui", response_class=HTMLResponse)
    def ui(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ) -> str:
        _require_access(x_admin_role, x_admin_token)
        return _admin_console_html()

    @router.get("/overview")
    def overview(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        window_seconds: int = 300,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return rt.dashboard.overview(window_seconds=window_seconds)

    @router.get("/integrity")
    def integrity(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        window_seconds: int = 300,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return rt.dashboard.integrity(window_seconds=window_seconds)

    @router.get("/throttle")
    def throttle(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        window_seconds: int = 300,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return rt.dashboard.throttle_view(window_seconds=window_seconds)

    @router.get("/s3")
    def s3_challenge(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        window_seconds: int = 300,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return rt.dashboard.s3_view(window_seconds=window_seconds)

    @router.get("/block")
    def block(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        window_seconds: int = 300,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return rt.dashboard.block_view(window_seconds=window_seconds)

    @router.get("/sessions")
    def sessions(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        if not session_id and not trace_id:
            raise HTTPException(status_code=400, detail="session_id or trace_id is required")
        return rt.dashboard.session_drilldown(session_id=session_id, trace_id=trace_id, limit=limit)

    @router.get("/policy")
    def policy(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return {
            "warehouse": rt.audit_warehouse.metadata(),
            "auditLog": str(rt.audit_logger.file_path),
            "current": rt.dashboard.policy_status(),
            "availableVersions": rt.policy_store.list_policy_versions(),
            "rolloutState": rt.offline_optimizer.current_rollout_state(),
            "pipeline": {
                "collector": rt.audit_collector.status(),
                "warehouse": rt.audit_warehouse.metadata(),
            },
        }

    @router.get("/pipeline")
    def pipeline(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return {
            "collector": rt.audit_collector.status(),
            "warehouse": rt.audit_warehouse.metadata(),
        }

    @router.get("/offline-summary")
    def offline_summary(
        x_admin_role: Optional[str] = Header(default=None, alias="X-Admin-Role"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ) -> dict[str, object]:
        _require_access(x_admin_role, x_admin_token)
        return {
            "latestSummary": rt.offline_optimizer.latest_summary(),
        }

    return ensure_route_handler_alias(router)


__all__ = ["create_admin_console_router"]


def _configured_tokens_for_role(role: str) -> list[str]:
    tokens: list[str] = []
    shared = os.environ.get(_ADMIN_SHARED_TOKEN_ENV, "").strip()
    if shared:
        tokens.append(shared)
    role_env = _ADMIN_ROLE_TOKEN_ENVS.get(role)
    if role_env:
        role_token = os.environ.get(role_env, "").strip()
        if role_token:
            tokens.append(role_token)
    return tokens


def _admin_console_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Defense Control Room</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 249, 238, 0.82);
      --panel-strong: #fff8ef;
      --ink: #122026;
      --muted: #5f6c6f;
      --line: rgba(18, 32, 38, 0.12);
      --accent: #bc5a2b;
      --accent-soft: rgba(188, 90, 43, 0.12);
      --good: #266b4e;
      --warn: #8b5a10;
      --shadow: 0 20px 60px rgba(73, 52, 31, 0.12);
      --radius: 22px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(188, 90, 43, 0.16), transparent 32%),
        radial-gradient(circle at top right, rgba(38, 107, 78, 0.10), transparent 28%),
        linear-gradient(180deg, #f8f2e8 0%, var(--bg) 100%);
      min-height: 100vh;
    }
    .shell {
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px 18px 64px;
    }
    .hero {
      display: grid;
      gap: 14px;
      margin-bottom: 24px;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: calc(var(--radius) + 6px);
      background: linear-gradient(135deg, rgba(255,248,239,0.92), rgba(255,252,247,0.72));
      box-shadow: var(--shadow);
    }
    .eyebrow {
      font-family: "Menlo", "Consolas", monospace;
      font-size: 12px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--accent);
    }
    h1 {
      margin: 0;
      font-size: clamp(2.2rem, 4vw, 4.4rem);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }
    .sub {
      max-width: 760px;
      color: var(--muted);
      font-size: 1rem;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .toolbar input, .toolbar button {
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 10px 14px;
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font: inherit;
    }
    .toolbar button {
      cursor: pointer;
      background: var(--ink);
      color: #fff6ea;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
    }
    .card {
      grid-column: span 4;
      padding: 18px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(10px);
      box-shadow: var(--shadow);
      transform: translateY(12px);
      opacity: 0;
      animation: rise 500ms ease forwards;
    }
    .card:nth-child(2) { animation-delay: 80ms; }
    .card:nth-child(3) { animation-delay: 140ms; }
    .card.wide { grid-column: span 6; }
    .card.full { grid-column: 1 / -1; }
    .card h2 {
      margin: 0 0 10px;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
    }
    .metric {
      display: grid;
      gap: 8px;
    }
    .metric strong {
      font-size: 2rem;
      line-height: 1;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      padding: 6px 10px;
      border-radius: 999px;
      font-family: "Menlo", "Consolas", monospace;
      font-size: 12px;
      background: var(--accent-soft);
      color: var(--accent);
    }
    .list, pre {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .list li {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 8px 0;
      border-top: 1px solid rgba(18, 32, 38, 0.08);
      font-family: "Menlo", "Consolas", monospace;
      font-size: 13px;
    }
    .list li:first-child { border-top: 0; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      padding: 14px;
      border-radius: 16px;
      background: rgba(18, 32, 38, 0.05);
      font-family: "Menlo", "Consolas", monospace;
      font-size: 12px;
      line-height: 1.55;
      max-height: 420px;
      overflow: auto;
    }
    .warn { color: var(--warn); }
    .good { color: var(--good); }
    @keyframes rise {
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 900px) {
      .card, .card.wide { grid-column: 1 / -1; }
      .shell { padding: 16px 12px 48px; }
      h1 { line-height: 1; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Traffic Master Defense / Control Room</div>
      <h1>Near Real-Time SSOT Console</h1>
      <div class="sub">decision_audit, local warehouse, rollout state, offline summary를 한 화면에서 확인한다. 기본 refresh는 5초다.</div>
      <div class="toolbar">
        <input id="role" value="admin_readonly" aria-label="admin role" />
        <input id="token" type="password" placeholder="admin token" aria-label="admin token" />
        <input id="sessionId" placeholder="sessionId" aria-label="session id" />
        <button id="reload">Reload</button>
      </div>
    </section>

    <section class="grid">
      <article class="card"><h2>Overview</h2><div id="overview" class="metric"></div></article>
      <article class="card"><h2>Integrity</h2><div id="integrity" class="metric"></div></article>
      <article class="card"><h2>Policy</h2><div id="policy" class="metric"></div></article>
      <article class="card wide"><h2>Throttle</h2><ul id="throttle" class="list"></ul></article>
      <article class="card wide"><h2>S3 Challenge</h2><pre id="s3"></pre></article>
      <article class="card full"><h2>Offline Summary</h2><pre id="summary"></pre></article>
      <article class="card full"><h2>Session Drilldown</h2><pre id="session"></pre></article>
    </section>
  </main>
  <script>
    const endpoints = {
      overview: "/admin/defense/overview",
      integrity: "/admin/defense/integrity",
      throttle: "/admin/defense/throttle",
      s3: "/admin/defense/s3",
      policy: "/admin/defense/policy",
      pipeline: "/admin/defense/pipeline",
      summary: "/admin/defense/offline-summary",
      session: "/admin/defense/sessions"
    };

    async function fetchJson(path, params = {}) {
      const url = new URL(path, window.location.origin);
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          url.searchParams.set(key, value);
        }
      });
      const role = document.getElementById("role").value || "admin_readonly";
      const token = document.getElementById("token").value || "";
      const headers = { "X-Admin-Role": role };
      if (token) {
        headers["X-Admin-Token"] = token;
      }
      const res = await fetch(url, { headers });
      if (!res.ok) {
        throw new Error(path + " -> " + res.status);
      }
      return res.json();
    }

    function metricBox(data) {
      return `
        <div class="pill">window ${data.windowSeconds ?? "-"}s</div>
        <strong>${data.requestRateRpm ?? "-"}</strong>
        <div>RPM</div>
        <div class="${(data.blockRate ?? 0) > 0.02 ? "warn" : "good"}">blockRate: ${data.blockRate ?? "-"}</div>
        <div>requireS3Rate: ${data.requireS3Rate ?? "-"}</div>
      `;
    }

    function integrityBox(data) {
      const warnings = (data.warnings || []).map((item) => `<div class="warn">${item}</div>`).join("");
      return `
        <div class="pill">dedup ${data.dedupDuplicateRate ?? "-"}</div>
        <strong>${data.missingFeatureRate ?? "-"}</strong>
        <div>missingFeatureRate</div>
        ${warnings || '<div class="good">no active warnings</div>'}
      `;
    }

    function policyBox(data) {
      return `
        <div class="pill">${data.current?.latestPolicyVersion || "unknown"}</div>
        <div>warehouse: ${data.warehouse?.backend || "-"}</div>
        <div>collector lag: ${data.pipeline?.collector?.lastIngestLagMs ?? "-"}</div>
        <div>versions: ${(data.availableVersions || []).join(", ") || "-"}</div>
        <div>rollout: ${data.rolloutState?.stage || "NONE"}</div>
      `;
    }

    function listItems(el, rows, keyA, keyB) {
      el.innerHTML = (rows || []).slice(0, 10).map((row) => `
        <li><span>${row[keyA]}</span><strong>${row[keyB]}</strong></li>
      `).join("") || "<li><span>No data</span><strong>-</strong></li>";
    }

    async function refresh() {
      try {
        const [overview, integrity, throttle, s3, policy, summary] = await Promise.all([
          fetchJson(endpoints.overview),
          fetchJson(endpoints.integrity),
          fetchJson(endpoints.throttle),
          fetchJson(endpoints.s3),
          fetchJson(endpoints.policy),
          fetchJson(endpoints.summary),
        ]);

        document.getElementById("overview").innerHTML = metricBox(overview);
        document.getElementById("integrity").innerHTML = integrityBox(integrity);
        document.getElementById("policy").innerHTML = policyBox(policy);
        listItems(document.getElementById("throttle"), throttle.topEndpoints, "endpointPath", "count");
        document.getElementById("s3").textContent = JSON.stringify(s3, null, 2);
        document.getElementById("summary").textContent = summary.latestSummary?.summaryText || "No summary yet";

        const sessionId = document.getElementById("sessionId").value;
        if (sessionId) {
          const session = await fetchJson(endpoints.session, { session_id: sessionId });
          document.getElementById("session").textContent = JSON.stringify(session, null, 2);
        } else {
          document.getElementById("session").textContent = "sessionId를 입력하면 drilldown이 로드된다.";
        }
      } catch (err) {
        document.getElementById("summary").textContent = String(err);
      }
    }

    document.getElementById("reload").addEventListener("click", refresh);
    refresh();
    window.setInterval(refresh, 5000);
  </script>
</body>
</html>"""
