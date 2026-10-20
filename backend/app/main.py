"""FastAPI routes. Thin layer: auth/CSRF/origin checks, then tenant-scoped services."""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agent.orchestrator import run_task
from .db import get_conn, init_schema
from .services import actions as action_svc
from .services import analysis, auth, export, workspace
from .services.errors import Actor, AppError

@asynccontextmanager
async def _lifespan(_app):
    init_schema(get_conn())
    yield


app = FastAPI(title="OrderBridge (synthetic demo)", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=_lifespan)
SESSION_COOKIE = "ob_session"
MUTATING = {"POST", "PATCH", "PUT", "DELETE"}


@app.exception_handler(AppError)
async def _app_error(request: Request, exc: AppError):
    body = {"code": exc.code, "user_message": exc.user_message, "request_id": request.state.request_id}
    if exc.field_errors:
        body["field_errors"] = exc.field_errors
    body.update(exc.extra)
    return JSONResponse(body, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError):
    fields = {".".join(str(x) for x in e["loc"][1:]): e["msg"] for e in exc.errors()}
    return JSONResponse({"code": "VALIDATION_ERROR", "user_message": "Request is not valid.", "field_errors": fields,
                         "request_id": request.state.request_id}, status_code=422)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):  # no stack traces or secrets to clients
    return JSONResponse({"code": "FAILED", "user_message": "Unexpected server error.", "request_id": getattr(request.state, "request_id", None)}, status_code=500)


@app.middleware("http")
async def _security(request: Request, call_next):
    request.state.request_id = "req_" + secrets.token_hex(6)
    origin = request.headers.get("origin")
    if request.method in MUTATING and origin and origin not in config.ALLOWED_ORIGINS:
        return JSONResponse({"code": "FORBIDDEN", "user_message": "Origin not allowed.", "request_id": request.state.request_id}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = request.state.request_id
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def current(request: Request, x_csrf_token: str | None = Header(default=None)) -> Actor:
    actor, csrf = auth.session_actor(request.cookies.get(SESSION_COOKIE))
    if request.method in MUTATING:
        auth.check_csrf(csrf, x_csrf_token)
    return actor


# ---------------------------------------------------------------- auth & workspace

class LoginBody(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: LoginBody):
    token, csrf, actor = auth.login(body.username, body.password)
    resp = JSONResponse({"user": {"username": actor.username, "role": actor.role, "display_name": actor.display_name}, "csrf_token": csrf})
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=config.SECURE_COOKIES, max_age=config.SESSION_TTL_SECONDS, path="/")
    return resp


@app.post("/api/auth/logout")
def logout(actor: Actor = Depends(current)):
    auth.logout(actor)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/workspace")
def get_workspace(request: Request, actor: Actor = Depends(current)):
    _, csrf = auth.session_actor(request.cookies.get(SESSION_COOKIE))
    b = workspace.business(actor)
    acct = workspace.active_account(actor.tenant_id)
    ev = workspace.evidence_list(actor)
    owner = actor.is_owner
    return {
        "user": {"username": actor.username, "role": actor.role, "display_name": actor.display_name}, "csrf_token": csrf,
        "business": {"business_id": b["business_id"], "name": b["name"], "currency": b["currency"], "timezone": b["timezone"],
                     "opening_cash_minor": b["opening_cash_minor"], "opening_date": b["opening_date"], "buffer_minor": b["buffer_minor"],
                     "horizon_end": b["horizon_end"], "input_version": b["input_version"], "synthetic": bool(b["synthetic"])},
        "record_count": len(ev["records"]), "blocking_issue_count": ev["blocking_issue_count"],
        "review_count": sum(1 for r in ev["records"] if r["confirmation_status"] in ("parsed_unconfirmed", "missing")),
        "sandbox": action_svc.sandbox_view(actor) if acct else None,
        "agent": {"mode": actor.agent_mode, "live_configured": config.anthropic_key_configured(), "model": config.ANTHROPIC_MODEL,
                  "label": "Live AI" if actor.agent_mode == "live" else "Rule-based replay"},
        "conditions": analysis.conditions(actor), "policy": config.POLICY,
        "permitted_operations": ["read"] + (["import", "correct", "accept_terms", "prepare", "approve", "execute"] if owner else []),
    }


@app.post("/api/workspace/load-example")
def load_example(actor: Actor = Depends(current)):
    return workspace.load_example(actor)


class ModeBody(BaseModel):
    mode: str


@app.post("/api/agent/mode")
def agent_mode(body: ModeBody, actor: Actor = Depends(current)):
    auth.set_agent_mode(actor, body.mode)
    return {"mode": body.mode}


# ---------------------------------------------------------------- imports & evidence

@app.post("/api/imports/preview")
async def import_preview(file: UploadFile = File(...), order_id: str | None = Form(default=None), actor: Actor = Depends(current)):
    data = await file.read(5 * 1024 * 1024 + 1)
    return workspace.preview_import(actor, file.filename or "upload.csv", data, order_id or None)


@app.get("/api/imports/{import_id}")
def import_get(import_id: str, actor: Actor = Depends(current)):
    return workspace.import_summary(actor, import_id)


class RowFix(BaseModel):
    changes: dict[str, Any]


@app.patch("/api/imports/{import_id}/rows/{row_number}")
def import_fix(import_id: str, row_number: int, body: RowFix, actor: Actor = Depends(current)):
    return workspace.correct_staged_row(actor, import_id, row_number, body.changes)


class CommitBody(BaseModel):
    expected_version: int


@app.post("/api/imports/{import_id}/commit")
def import_commit(import_id: str, body: CommitBody, actor: Actor = Depends(current)):
    return workspace.commit_import(actor, import_id, body.expected_version)


@app.get("/api/evidence")
def evidence(actor: Actor = Depends(current)):
    return workspace.evidence_list(actor)


@app.get("/api/evidence/{event_id}")
def evidence_one(event_id: str, actor: Actor = Depends(current)):
    return workspace.evidence_detail(actor, event_id)


class RecordPatch(BaseModel):
    changes: dict[str, Any]
    expected_record_version: int


@app.patch("/api/records/{event_id}")
def patch_record(event_id: str, body: RecordPatch, actor: Actor = Depends(current)):
    return workspace.correct_record(actor, event_id, body.changes, body.expected_record_version)


# ---------------------------------------------------------------- analysis

class ForecastBody(BaseModel):
    scenario_id: str
    horizon_end: str | None = None
    extend_horizon: bool = True


@app.post("/api/forecasts")
def forecast(body: ForecastBody, actor: Actor = Depends(current)):
    return analysis.run_forecast(actor, body.scenario_id, body.horizon_end, body.extend_horizon)


@app.get("/api/forecasts/{run_id}")
def forecast_get(run_id: str, actor: Actor = Depends(current)):
    return analysis.get_run(actor, run_id)


class CompareBody(BaseModel):
    scenario_ids: list[str] | None = None
    expected_input_version: int | None = None


@app.post("/api/comparisons")
def comparisons(body: CompareBody, actor: Actor = Depends(current)):
    comp = analysis.compare(actor, body.scenario_ids, body.expected_input_version)
    comp["decision"] = analysis.decision(actor, comp)
    comp["decision"]["execution_mode"] = "calculation"
    comp["financing_options"] = analysis.financing_options(actor) if any(s["required_support_minor"] for s in comp["scenarios"]) else []
    return comp


class ConditionBody(BaseModel):
    condition_id: str
    accept: bool


@app.post("/api/scenarios/{scenario_id}/conditions")
def scenario_condition(scenario_id: str, body: ConditionBody, actor: Actor = Depends(current)):
    sdef = next((s for s in analysis.scenario_defs()["scenarios"] if s["scenario_id"] == scenario_id), None)
    if not sdef or body.condition_id not in sdef["conditions"]:
        raise AppError("VALIDATION_ERROR", "Condition does not belong to this scenario.")
    return {"conditions": analysis.set_condition(actor, body.condition_id, body.accept)}


@app.get("/api/financing")
def financing(purpose: str = "working_capital", actor: Actor = Depends(current)):
    return analysis.financing_options(actor, purpose)


# ---------------------------------------------------------------- agent

class AgentBody(BaseModel):
    task: str = "analyze_order"
    question: str | None = Field(default=None, max_length=500)
    action_id: str | None = None
    mode: str | None = None


@app.post("/api/agent/tasks")
def agent_task(body: AgentBody, actor: Actor = Depends(current)):
    return run_task(actor, body.task, mode=body.mode or actor.agent_mode, question=body.question, action_id=body.action_id)


# ---------------------------------------------------------------- sandbox & actions

@app.post("/api/sandbox/initialize")
def sandbox_init(actor: Actor = Depends(current)):
    return action_svc.initialize_sandbox(actor)


@app.get("/api/sandbox")
def sandbox_get(actor: Actor = Depends(current)):
    return action_svc.sandbox_view(actor)


class PrepareBody(BaseModel):
    scenario_id: str
    obligation_event_id: str
    recipient_id: str
    amount: str
    idempotency_key: str = Field(max_length=100)
    action_type: str = "sandbox_supplier_payment"


@app.post("/api/actions/prepare")
def prepare(body: PrepareBody, actor: Actor = Depends(current)):
    return action_svc.prepare_payment(actor, scenario_id=body.scenario_id, obligation_event_id=body.obligation_event_id, recipient_id=body.recipient_id,
                                      amount=body.amount, idempotency_key=body.idempotency_key, action_type=body.action_type)


class ApproveBody(BaseModel):
    payload_hash: str


@app.post("/api/actions/{action_id}/approve")
def approve(action_id: str, body: ApproveBody, actor: Actor = Depends(current)):
    return action_svc.approve(actor, action_id, body.payload_hash)


@app.post("/api/actions/{action_id}/execute")
def execute(action_id: str, actor: Actor = Depends(current), idempotency_key: str | None = Header(default=None)):
    return action_svc.execute(actor, action_id, idempotency_key=idempotency_key)


@app.post("/api/actions/{action_id}/cancel")
def cancel(action_id: str, actor: Actor = Depends(current)):
    return action_svc.cancel(actor, action_id)


@app.get("/api/actions")
def actions_list(actor: Actor = Depends(current)):
    return action_svc.list_actions(actor)


@app.get("/api/actions/{action_id}")
def action_get(action_id: str, actor: Actor = Depends(current)):
    return action_svc.action_view(actor, action_id)


# ---------------------------------------------------------------- audit & export

@app.get("/api/audit")
def audit_get(actor: Actor = Depends(current)):
    return export.audit_log(actor)


@app.get("/api/export")
def export_get(format: str = "json", actor: Actor = Depends(current)):
    if format == "zip":
        return Response(export.evidence_zip(actor), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="orderbridge-evidence.zip"'})
    if format == "csv":
        return Response(export.events_csv(actor), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="cash_events.csv"'})
    return export.evidence_bundle(actor)


@app.get("/api/health")
def health():
    try:
        get_conn().execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unavailable",
            "live_model_configured": config.anthropic_key_configured(), "model": config.ANTHROPIC_MODEL, "synthetic_demo": True}


# ---------------------------------------------------------------- static frontend (single-process demo)

if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise AppError("NOT_FOUND", "Not found.", 404)
        return FileResponse(config.FRONTEND_DIST / "index.html")
