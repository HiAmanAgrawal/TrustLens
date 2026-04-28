"""
Developer testing portal for the TrustLens conversational agent.

Mounted at /testing — only enabled when APP_ENV != 'production'.

Provides:
  GET  /testing/            → browser-based UI
  POST /testing/send        → invoke the agent, returns full trace + state
  GET  /testing/session/{wa_id} → read current Redis onboarding session
  DELETE /testing/session/{wa_id} → clear Redis session (restart onboarding)
"""

from __future__ import annotations

import dataclasses
import logging
import time as _t
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.models.enums import MessageDirectionEnum

logger = logging.getLogger(__name__)
router = APIRouter()

TRACKED_NODES = {"router", "onboarding", "existing_user_greeting"}


# ── Pydantic models ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    wa_id: str = "whatsapp:+919876543210"
    message: str


class NodeTrace(BaseModel):
    node: str
    duration_ms: float
    changes: dict[str, Any]


class AgentResponse(BaseModel):
    response: str
    trace: list[NodeTrace]
    final_state: dict[str, Any]
    redis_session: dict[str, Any] | None
    db_messages: list[dict[str, Any]]
    db_user: dict[str, Any] | None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def portal_ui() -> HTMLResponse:
    return HTMLResponse(_PORTAL_HTML)


@router.post("/send", response_model=AgentResponse)
async def send(req: ChatRequest, db: AsyncSession = Depends(get_async_session)) -> AgentResponse:
    """
    Simulate one inbound WhatsApp message and return the full agent trace.

    Runs the LangGraph graph with stream_mode="updates" so every node's output
    is captured as a distinct trace entry. Also saves inbound + outbound messages
    to DB (same as the production webhook) so the greeting context stays current.
    """
    from app.agents import conversation_graph
    from app.agents.nodes.router import _find_user_by_wa_id
    from app.services.message_service import get_recent_messages, save_message
    from app.services.session_service import get_session as get_redis_session

    error: str | None = None
    trace: list[NodeTrace] = []
    final_state: dict[str, Any] = {}

    initial_state: dict[str, Any] = {
        "whatsapp_user_id": req.wa_id,
        "phone_number": req.wa_id.replace("whatsapp:", ""),
        "incoming_text": req.message,
        "incoming_media_url": None,
        "incoming_media_type": None,
        "lang": "en",
        "is_new_user": False,
        "onboarding_step": None,
        "db_user_id": None,
        "db_user_name": None,
        "db_user_diet": None,
        "session_data": None,
        "response_text": "",
        "response_sent": False,
    }
    final_state = dict(initial_state)

    try:
        # Persist inbound message (same as production webhook)
        await save_message(
            db,
            whatsapp_user_id=req.wa_id,
            direction=MessageDirectionEnum.INBOUND,
            message_text=req.message,
        )

        config = {"configurable": {"db_session": db}}

        # Stream node-by-node updates for the trace
        t_prev = _t.monotonic()
        async for chunk in conversation_graph.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            t_now = _t.monotonic()
            for node_name, changes in chunk.items():
                if isinstance(changes, dict):
                    duration_ms = round((t_now - t_prev) * 1000, 1)
                    sanitized = _sanitize(changes)
                    trace.append(NodeTrace(
                        node=node_name,
                        duration_ms=duration_ms,
                        changes=sanitized,
                    ))
                    final_state.update(changes)
            t_prev = t_now

        reply = str(final_state.get("response_text") or "")

        # Persist outbound reply
        if reply:
            await save_message(
                db,
                whatsapp_user_id=req.wa_id,
                direction=MessageDirectionEnum.OUTBOUND,
                message_text=reply,
            )

        await db.commit()

    except Exception as exc:
        logger.exception("testing.send | agent error wa_id=%r", req.wa_id)
        error = f"{type(exc).__name__}: {exc}"
        try:
            await db.rollback()
        except Exception:
            pass
        reply = ""

    # ── Fetch current state from Redis + DB ────────────────────────────────
    redis_session_obj = None
    try:
        redis_session_obj = await get_redis_session(req.wa_id)
    except Exception as exc:
        logger.warning("testing.send | redis fetch failed: %s", exc)

    db_messages: list[dict[str, Any]] = []
    db_user: dict[str, Any] | None = None
    try:
        msgs = await get_recent_messages(db, whatsapp_user_id=req.wa_id, limit=30)
        db_messages = [_message_to_dict(m) for m in msgs]
        user = await _find_user_by_wa_id(db, req.wa_id)
        db_user = await _user_to_dict(user)
    except Exception as exc:
        logger.warning("testing.send | db fetch failed: %s", exc)

    return AgentResponse(
        response=reply,
        trace=trace,
        final_state=_sanitize(final_state),
        redis_session=dataclasses.asdict(redis_session_obj) if redis_session_obj else None,
        db_messages=db_messages,
        db_user=db_user,
        error=error,
    )


@router.get("/session/{wa_id}")
async def get_session(wa_id: str) -> dict:
    """Return current Redis onboarding session for a WhatsApp user."""
    from app.services.session_service import get_session as _get
    sess = await _get(wa_id)
    return {"session": dataclasses.asdict(sess) if sess else None}


@router.delete("/session/{wa_id}")
async def clear_session(wa_id: str) -> dict:
    """Delete the Redis onboarding session — resets the user to 'new user' state."""
    from app.services.session_service import delete_session
    await delete_session(wa_id)
    logger.info("testing.session.cleared | wa_id=%r", wa_id)
    return {"cleared": True, "wa_id": wa_id}


@router.post("/scan")
async def testing_scan_upload(
    image: UploadFile = File(...),
    scan_type: str = Form("unified"),
    user_id: str | None = Form(None),
    wa_id: str | None = Form(None),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Testing proxy for Phase 3 scan pipelines.

    Accepts a multipart image upload and routes to the appropriate pipeline
    (unified / prescription / grocery). Returns the typed pipeline result as JSON.
    """
    import uuid as _uuid

    from app.services.pipeline_service import (
        run_grocery_scan,
        run_prescription_scan,
        run_unified_scan,
    )

    image_bytes = await image.read()
    uid: _uuid.UUID | None = None
    if user_id:
        try:
            uid = _uuid.UUID(user_id)
        except ValueError:
            pass

    logger.info(
        "testing.scan | scan_type=%r filename=%r bytes=%d user_id=%s",
        scan_type, image.filename, len(image_bytes), uid,
    )

    # Tie the product context to the WhatsApp user ID so follow-up questions
    # in the same chat panel automatically carry the scan context.
    session_id = wa_id or f"testing:{uid or 'anon'}"

    try:
        if scan_type == "prescription":
            result = await run_prescription_scan(db, image_bytes=image_bytes, user_id=uid)
            await db.commit()
            payload = {"scan_type": "prescription", "result": result.model_dump()}

        elif scan_type == "grocery":
            _event, result = await run_grocery_scan(db, image_bytes=image_bytes, user_id=uid)
            await db.commit()
            payload = {"scan_type": "grocery", "result": result.model_dump()}
            # Store context for follow-up Q&A
            from app.services.product_context import (
                build_context_from_grocery_response,
                store_product_context,
            )
            ctx = build_context_from_grocery_response(result, session_id)
            await store_product_context(session_id, ctx)
            payload["session_id"] = session_id

        else:  # unified (default)
            result = await run_unified_scan(db, image_bytes=image_bytes, user_id=uid, lang="en")
            await db.commit()
            payload = {"scan_type": "unified", "result": result.model_dump()}
            # Store context based on which sub-pipeline ran
            from app.services.product_context import (
                build_context_from_grocery_response,
                build_context_from_medicine_response,
                store_product_context,
            )
            if result.grocery:
                ctx = build_context_from_grocery_response(result.grocery, session_id)
                await store_product_context(session_id, ctx)
                payload["session_id"] = session_id
            elif result.medicine:
                ctx = build_context_from_medicine_response(result.medicine, session_id)
                await store_product_context(session_id, ctx)
                payload["session_id"] = session_id

        logger.info("testing.scan | done scan_type=%r session_id=%r", scan_type, session_id)
        return payload

    except Exception as exc:
        logger.exception("testing.scan | error scan_type=%r", scan_type)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"error": f"{type(exc).__name__}: {exc}"}


@router.post("/ask")
async def testing_ask(
    session_id: str = Form(...),
    question: str = Form(...),
    db: AsyncSession = Depends(get_async_session),   # noqa: ARG001 — kept for consistency
) -> dict:
    """
    Ask a follow-up question about the last scanned product.

    Retrieves the product context stored by /testing/scan and passes it to
    the LangGraph product advisor agent. Returns the agent's answer + tools used.
    """
    logger.info("testing.ask | session_id=%r question=%r", session_id, question[:100])

    from app.services.product_context import get_product_context
    from app.agents.product_advisor.graph import run_product_advisor

    product_context = await get_product_context(session_id)
    if not product_context:
        logger.warning("testing.ask | no context for session=%r", session_id)

    result = await run_product_advisor(
        question,
        product_context=product_context,
        session_id=session_id,
    )
    return {
        "answer": result["answer"],
        "tools_called": result["tools_called"],
        "error": result.get("error"),
        "context_found": product_context is not None,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize(obj: Any) -> Any:
    """Recursively convert any value to a JSON-safe type."""
    import enum
    import uuid
    from datetime import date, datetime

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _sanitize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


def _message_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "id": str(msg.id),
        "direction": msg.direction.value if hasattr(msg.direction, "value") else str(msg.direction),
        "message_type": msg.message_type.value if hasattr(msg.message_type, "value") else str(msg.message_type),
        "message_text": msg.message_text or "",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


async def _user_to_dict(user: Any) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "whatsapp_user_id": user.whatsapp_user_id,
        "phone_number": user.phone_number,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "health_profile": {
            "dietary_preference": user.health_profile.dietary_preference.value
            if user.health_profile and user.health_profile.dietary_preference
            else None
        } if user.health_profile else None,
        "allergies": [
            {
                "allergen": a.allergen,
                "allergen_category": a.allergen_category.value if a.allergen_category else None,
            }
            for a in (user.allergies or [])
        ],
        "medical_conditions": [
            {"condition_name": c.condition_name, "is_active": c.is_active}
            for c in (user.medical_conditions or [])
            if c.is_active
        ],
    }


# ── HTML UI ───────────────────────────────────────────────────────────────────

_PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TrustLens — Agent Testing Portal</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;height:100vh;display:flex;flex-direction:column;overflow:hidden}

header{background:#1e293b;border-bottom:1px solid #334155;padding:10px 20px;display:flex;align-items:center;gap:10px;flex-shrink:0}
.hlogo{font-size:16px;font-weight:700;color:#38bdf8}
.hbadge{background:#0c4a6e;color:#7dd3fc;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600}
.hsub{margin-left:auto;font-size:12px;color:#475569}

.main{display:flex;flex:1;overflow:hidden}

/* ── Chat panel ─────────────────────────── */
.chat-panel{width:42%;min-width:300px;border-right:1px solid #1e293b;display:flex;flex-direction:column}
.chat-hdr{padding:10px 14px;border-bottom:1px solid #1e293b;background:#0f172a}
.chat-hdr label{font-size:10px;text-transform:uppercase;color:#64748b;letter-spacing:.8px}
.wa-input{width:100%;background:#1e293b;border:1px solid #334155;color:#93c5fd;padding:5px 9px;border-radius:6px;font-size:12px;font-family:monospace;margin-top:3px}
.wa-input:focus{outline:none;border-color:#38bdf8}

.chat-msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}

.msg-row{display:flex}
.msg-row.user{justify-content:flex-end}
.msg-wrap{max-width:82%}
.bubble{padding:8px 12px;border-radius:10px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.bubble.user{background:#0369a1;color:#fff;border-bottom-right-radius:3px}
.bubble.bot{background:#1e293b;color:#e2e8f0;border-bottom-left-radius:3px}
.bubble.err{background:#450a0a;color:#fca5a5}
.msg-meta{font-size:10px;color:#475569;margin-top:3px;display:flex;align-items:center;gap:5px}
.msg-row.user .msg-meta{justify-content:flex-end}
.t-badge{background:#0c4a6e;color:#38bdf8;padding:1px 6px;border-radius:8px;font-size:10px}

.chat-foot{padding:10px 14px;border-top:1px solid #1e293b;background:#0a0f1a}
.loading{display:none;align-items:center;gap:6px;color:#38bdf8;font-size:12px;margin-bottom:6px}
.spin{width:14px;height:14px;border:2px solid #1e3a5f;border-top-color:#38bdf8;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.inp-row{display:flex;gap:7px}
.msg-ta{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:7px 10px;border-radius:7px;font-size:13px;resize:none;height:58px;font-family:inherit}
.msg-ta:focus{outline:none;border-color:#38bdf8}
.send-btn{background:#0284c7;color:#fff;border:none;padding:0 14px;border-radius:7px;cursor:pointer;font-size:13px;font-weight:600;height:38px;align-self:flex-end;transition:background .15s}
.send-btn:hover{background:#0369a1}
.send-btn:disabled{background:#1e293b;color:#475569;cursor:not-allowed}

/* ── Info panel ─────────────────────────── */
.info-panel{flex:1;display:flex;flex-direction:column;min-width:0}
.tab-bar{display:flex;border-bottom:1px solid #1e293b;background:#0a0f1a;flex-shrink:0;overflow-x:auto}
.tab{padding:9px 14px;font-size:12px;cursor:pointer;color:#64748b;border-bottom:2px solid transparent;white-space:nowrap;user-select:none;transition:color .15s}
.tab:hover{color:#94a3b8}
.tab.active{color:#38bdf8;border-bottom-color:#38bdf8}
.tab-body{flex:1;overflow-y:auto;padding:14px}
.pane{display:none}
.pane.active{display:block}

/* empty state */
.empty{color:#334155;font-size:13px;text-align:center;padding:40px 20px}

/* ── Trace ───────────────────────────────── */
.node-card{background:#1e293b;border:1px solid #273549;border-radius:8px;padding:12px 14px;margin-bottom:10px}
.nc-hdr{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.nc-idx{color:#475569;font-size:11px;min-width:16px}
.nbadge{font-size:11px;font-weight:700;padding:2px 9px;border-radius:10px;text-transform:uppercase;letter-spacing:.5px}
.nb-router{background:#1e3a5f;color:#38bdf8}
.nb-onboarding{background:#431407;color:#fb923c}
.nb-existing_user_greeting{background:#052e16;color:#4ade80}
.nb-default{background:#1e293b;color:#94a3b8}
.dur{margin-left:auto;font-size:11px;color:#64748b;background:#0f172a;padding:2px 7px;border-radius:7px;font-family:monospace}

.ch-table{width:100%;border-collapse:collapse;font-size:12px}
.ch-table th{color:#475569;font-size:10px;text-transform:uppercase;text-align:left;padding:3px 0;border-bottom:1px solid #334155;letter-spacing:.6px}
.ch-table td{padding:3px 0;vertical-align:top}
.ch-table td:first-child{color:#7dd3fc;font-family:monospace;width:38%;padding-right:8px}
.ch-table td:last-child{color:#e2e8f0;font-family:monospace;word-break:break-all}
.v-null{color:#475569!important;font-style:italic}
.v-true{color:#4ade80!important}
.v-false{color:#f87171!important}
.v-num{color:#67e8f9!important}

/* ── JSON viewer ─────────────────────────── */
.jv{font-family:'Menlo','Monaco','Courier New',monospace;font-size:12px;line-height:1.65;background:#1e293b;padding:14px;border-radius:8px;overflow-x:auto;white-space:pre}
.jk{color:#93c5fd}.js{color:#fde68a}.jn{color:#67e8f9}.jb{color:#fb923c}.jz{color:#6b7280}

/* ── Session ─────────────────────────────── */
.sess-actions{display:flex;gap:7px;margin-bottom:12px}
.btn-del{background:#450a0a;color:#fca5a5;border:1px solid #7f1d1d;padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer}
.btn-del:hover{background:#7f1d1d}
.btn-ref{background:#1e293b;color:#94a3b8;border:1px solid #334155;padding:5px 12px;border-radius:6px;font-size:12px;cursor:pointer}
.btn-ref:hover{color:#e2e8f0}

/* ── Messages table ──────────────────────── */
.mt{width:100%;border-collapse:collapse;font-size:12px}
.mt th{background:#1e293b;color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:.8px;padding:7px 9px;text-align:left;border-bottom:1px solid #334155}
.mt td{padding:7px 9px;border-bottom:1px solid #0f172a;vertical-align:top}
.mt tr:hover td{background:#1e293b55}
.dir-in{background:#052e16;color:#4ade80;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}
.dir-out{background:#0c4a6e;color:#38bdf8;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}

/* ── User profile ────────────────────────── */
.prof-sect{background:#1e293b;border:1px solid #273549;border-radius:8px;padding:12px 14px;margin-bottom:10px}
.plabel{font-size:10px;text-transform:uppercase;color:#64748b;letter-spacing:.8px;margin-bottom:5px}
.pval{font-size:13px;color:#e2e8f0}
.ptags{display:flex;flex-wrap:wrap;gap:6px}
.tag{background:#0f172a;border:1px solid #334155;color:#94a3b8;padding:2px 8px;border-radius:10px;font-size:12px}

/* ── Scrollbar ───────────────────────────── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#334155;border-radius:3px}
</style>
</head>
<body>
<header>
  <span class="hlogo">🔍 TrustLens</span>
  <span class="hbadge">Agent Testing Portal</span>
  <span class="hsub">Simulate WhatsApp messages · inspect nodes, state &amp; memory</span>
</header>

<div class="main">

  <!-- ── Chat panel ───────────────────────────────────────────────── -->
  <div class="chat-panel">
    <div class="chat-hdr">
      <label>WhatsApp User ID (wa_id)</label>
      <input id="waId" class="wa-input" value="whatsapp:+919876543210">
    </div>

    <div id="chatMsgs" class="chat-msgs">
      <div class="empty">Send a message to simulate a WhatsApp conversation.<br><br>
        <small>Try "Hi" to start onboarding, or use an existing user's wa_id.</small></div>
    </div>

    <div class="chat-foot">
      <!-- Image attach preview — shown above input when a file is chosen -->
      <div id="attachPreview" style="display:none;align-items:center;gap:8px;background:#0c1a2e;border:1px solid #0284c7;border-radius:7px;padding:6px 10px;margin-bottom:6px">
        <img id="attachThumb" style="width:40px;height:40px;object-fit:cover;border-radius:4px;border:1px solid #334155">
        <div style="flex:1;min-width:0">
          <div id="attachName" style="font-size:11px;color:#7dd3fc;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></div>
          <select id="attachScanType" style="background:#1e293b;border:1px solid #334155;color:#94a3b8;font-size:10px;padding:2px 4px;border-radius:4px;margin-top:2px">
            <option value="unified">Auto-detect</option>
            <option value="grocery">Grocery</option>
            <option value="prescription">Prescription</option>
          </select>
        </div>
        <button onclick="clearAttach()" style="background:none;border:none;color:#475569;font-size:16px;cursor:pointer;padding:0 4px" title="Remove">✕</button>
      </div>
      <!-- Product context indicator — shown after a scan is complete -->
      <div id="ctxIndicator" style="display:none;align-items:center;gap:6px;font-size:11px;color:#64748b;margin-bottom:5px;padding:4px 8px;background:#0f172a;border-radius:5px;border:1px solid #1e293b">
        <span id="ctxLabel" style="flex:1">📦 Product context active — follow-up questions go to the advisor</span>
        <button onclick="clearProductCtx()" style="background:none;border:none;color:#475569;font-size:11px;cursor:pointer;padding:0" title="Clear scan context">✕ clear</button>
      </div>
      <div id="loadEl" class="loading"><div class="spin"></div><span id="loadText">Agent thinking…</span></div>
      <div class="inp-row">
        <button id="attachBtn" onclick="document.getElementById('chatFileInput').click()" title="Attach product image"
          style="background:#1e293b;border:1px solid #334155;color:#64748b;width:36px;height:36px;border-radius:7px;font-size:16px;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center;align-self:flex-end;transition:color .15s"
          onmouseover="this.style.color='#38bdf8'" onmouseout="this.style.color='#64748b'">📎</button>
        <input id="chatFileInput" type="file" accept="image/*" style="display:none" onchange="chatFileChosen(this)">
        <textarea id="msgInput" class="msg-ta" placeholder="Type a message… or attach an image to scan a product"></textarea>
        <button id="sendBtn" class="send-btn" onclick="sendMsg()">Send ↵</button>
      </div>
    </div>
  </div>

  <!-- ── Info panel ───────────────────────────────────────────────── -->
  <div class="info-panel">
    <div class="tab-bar">
      <div class="tab active"  onclick="tab('trace')">🔀 Trace</div>
      <div class="tab"         onclick="tab('state')">📦 State</div>
      <div class="tab"         onclick="tab('session')">💾 Session</div>
      <div class="tab"         onclick="tab('messages')">💬 Messages</div>
      <div class="tab"         onclick="tab('user')">👤 User Profile</div>
    </div>
    <div class="tab-body">
      <div id="pane-trace"   class="pane active"><div class="empty">Run a message to see the node execution trace.</div></div>
      <div id="pane-state"   class="pane"><div class="empty">Run a message to see the final ConversationState.</div></div>
      <div id="pane-session" class="pane">
        <div class="sess-actions">
          <button class="btn-del" onclick="clearSess()">🗑 Reset Session</button>
          <button class="btn-ref" onclick="refreshSess()">↻ Refresh</button>
        </div>
        <div id="sessContent" class="empty">Run a message to see the Redis onboarding session.</div>
      </div>
      <div id="pane-messages" class="pane"><div id="msgsContent" class="empty">Run a message to see DB conversation history.</div></div>
      <div id="pane-user"    class="pane"><div id="userContent"  class="empty">Run a message to see the DB user profile.</div></div>
    </div>
  </div>

</div><!-- .main -->

<script>
// ── Tab management ──────────────────────────────────────────────────────────
function tab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('active'));
  const tabs=[...document.querySelectorAll('.tab')];
  const names=['trace','state','session','messages','user'];
  tabs[names.indexOf(name)]?.classList.add('active');
  document.getElementById('pane-'+name)?.classList.add('active');
}

// ── State ───────────────────────────────────────────────────────────────────
let _sessionId = null;   // set after scan; routes text messages to advisor
let _chatFile  = null;   // set when user picks a file via 📎

// ── File attachment ─────────────────────────────────────────────────────────
function chatFileChosen(inp){
  const f = inp.files[0];
  if(!f) return;
  _chatFile = f;
  document.getElementById('attachThumb').src = URL.createObjectURL(f);
  document.getElementById('attachName').textContent = f.name + '  ·  ' + (f.size/1024).toFixed(1) + ' KB';
  document.getElementById('attachPreview').style.display = 'flex';
}

function clearAttach(){
  _chatFile = null;
  document.getElementById('chatFileInput').value = '';
  document.getElementById('attachPreview').style.display = 'none';
}

function clearProductCtx(){
  _sessionId = null;
  document.getElementById('ctxIndicator').style.display = 'none';
}

// ── Send (routes: scan ▸ advisor ▸ agent) ───────────────────────────────────
async function sendMsg(){
  const waId = document.getElementById('waId').value.trim();
  const msg   = document.getElementById('msgInput').value.trim();
  if(!waId) return;
  if(!_chatFile && !msg) return;

  document.getElementById('sendBtn').disabled = true;
  document.getElementById('loadEl').style.display = 'flex';
  document.getElementById('msgInput').value = '';
  const t0 = Date.now();

  try{

    // ── Route 1: file attached → product scan ──────────────────────────────
    if(_chatFile){
      const scanType = document.getElementById('attachScanType').value;
      addBubble('user','📎 '+_chatFile.name+(msg?'\n'+msg:''));
      document.getElementById('loadText').textContent = 'Scanning product…';

      const fd = new FormData();
      fd.append('image', _chatFile, _chatFile.name);
      fd.append('scan_type', scanType);
      fd.append('wa_id', waId);
      clearAttach();

      const r = await fetch('/testing/scan',{method:'POST',body:fd});
      const d = await r.json();
      const elapsed = Date.now()-t0;

      if(d.error){
        addBubble('bot','⚠️ Scan failed: '+d.error,null,true);
      } else {
        addScanBubble(d, elapsed+'ms');
        if(d.session_id){
          _sessionId = d.session_id;
          const pe = d.result?.product_extraction
                  || d.result?.grocery?.product_extraction
                  || {};
          const label = pe.brand_name || pe.product_name || '';
          document.getElementById('ctxLabel').textContent =
            label ? '📦 '+label+' — follow-ups go to the advisor'
                  : '📦 Product context active — follow-ups go to the advisor';
          document.getElementById('ctxIndicator').style.display = 'flex';
        }
      }
      return;
    }

    // ── Route 2: product context active → advisor ──────────────────────────
    if(_sessionId){
      addBubble('user', msg);
      document.getElementById('loadText').textContent = 'Advisor thinking…';

      const fd = new FormData();
      fd.append('session_id', _sessionId);
      fd.append('question', msg);

      const r = await fetch('/testing/ask',{method:'POST',body:fd});
      const d = await r.json();
      const elapsed = Date.now()-t0;

      if(d.error && !d.answer){
        addBubble('bot','⚠️ '+d.error,null,true);
      } else {
        addAdvisorBubble(d.answer||'(no answer)', d.tools_called||[], elapsed+'ms');
      }
      if(!d.context_found){
        addBubble('bot','⚠️ Product context expired. Scan a product to start a new session.',null,true);
        clearProductCtx();
      }
      return;
    }

    // ── Route 3: regular WhatsApp agent ───────────────────────────────────
    addBubble('user', msg);
    document.getElementById('loadText').textContent = 'Agent thinking…';

    const r = await fetch('/testing/send',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wa_id:waId,message:msg})
    });
    const d = await r.json();
    const elapsed = Date.now()-t0;

    if(d.error){
      addBubble('bot','⚠️ '+d.error,null,true);
    } else {
      addBubble('bot',d.response||'(empty response)',elapsed+'ms');
    }
    renderTrace(d.trace||[]);
    renderState(d.final_state||{});
    renderSession(d.redis_session);
    renderMsgs(d.db_messages||[]);
    renderUser(d.db_user);
    tab('trace');

  }catch(e){
    addBubble('bot','⚠️ Request failed: '+e.message,null,true);
  }finally{
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('loadEl').style.display = 'none';
    document.getElementById('loadText').textContent = 'Agent thinking…';
  }
}

// ── Plain chat bubble ────────────────────────────────────────────────────────
function addBubble(side,text,timing,isErr){
  const c=document.getElementById('chatMsgs');
  if(c.querySelector('.empty'))c.innerHTML='';

  const row=document.createElement('div');
  row.className='msg-row '+side;
  const wrap=document.createElement('div');
  wrap.className='msg-wrap';
  const b=document.createElement('div');
  b.className='bubble '+(isErr?'err':side);
  b.textContent=text;
  const meta=document.createElement('div');
  meta.className='msg-meta';
  meta.textContent=new Date().toLocaleTimeString();
  if(timing){const t=document.createElement('span');t.className='t-badge';t.textContent=timing;meta.appendChild(t);}
  wrap.appendChild(b);wrap.appendChild(meta);
  row.appendChild(wrap);
  c.appendChild(row);
  c.scrollTop=c.scrollHeight;
}

// ── Compact scan result bubble ───────────────────────────────────────────────
function addScanBubble(d, timing){
  const c = document.getElementById('chatMsgs');
  if(c.querySelector('.empty')) c.innerHTML='';

  const r  = d.result || {};
  const st = d.scan_type || 'unified';
  const groc = r.grocery || (st==='grocery' ? r : null);
  const med  = r.medicine || (st==='medicine' ? r : null);
  const pres = st==='prescription';
  const pe   = r.product_extraction || groc?.product_extraction || {};

  const lines = [];

  if(pres){
    lines.push('📋 Prescription scanned');
    const n = (r.medicine_cards||[]).length;
    if(n) lines.push(`💊 ${n} medicine${n>1?'s':''} identified`);
  } else if(groc){
    const rb = groc.risk_band || 'unknown';
    const rE = {low:'✅',medium:'⚠️',high:'❌'}[rb]||'❓';
    const brand = pe.brand_name || pe.product_name || groc.product_extraction?.brand_name || '';
    lines.push(brand ? `📦 ${brand}` : '📦 Grocery product scanned');
    lines.push(`${rE} Risk: ${rb.toUpperCase()}`+(groc.expiry_status?` · Expiry: ${groc.expiry_status}`:''));
    const ingN = groc.ingredients_count || pe.ingredients?.length || null;
    if(ingN) lines.push(`🧪 ${ingN} ingredients`);
    (groc.findings||[]).filter(f=>f.severity==='error'||f.severity==='warning').slice(0,2)
      .forEach(f=>lines.push(`• ${f.message}`));
    if(groc.fssai?.online_status==='valid') lines.push('✅ FSSAI verified');
    else if(groc.fssai?.online_status==='invalid') lines.push('❌ FSSAI issue found');
  } else if(med){
    lines.push(med.brand_name ? `💊 ${med.brand_name}` : '💊 Medicine scanned');
    if(med.verdict) lines.push(`Verdict: ${med.verdict}`);
    if(med.expiry_status) lines.push(`Expiry: ${med.expiry_status}`);
  } else {
    lines.push('📷 Scan complete');
  }

  if(d.session_id && !pres){
    lines.push('');
    lines.push('💬 Ask me anything about this product!');
  }

  const row=document.createElement('div');
  row.className='msg-row';
  const wrap=document.createElement('div');
  wrap.className='msg-wrap';
  const b=document.createElement('div');
  b.className='bubble bot';
  b.textContent=lines.join('\n');
  const meta=document.createElement('div');
  meta.className='msg-meta';
  meta.textContent=new Date().toLocaleTimeString();
  if(timing){const t=document.createElement('span');t.className='t-badge';t.textContent=timing;meta.appendChild(t);}
  wrap.appendChild(b);wrap.appendChild(meta);
  row.appendChild(wrap);
  c.appendChild(row);
  c.scrollTop=c.scrollHeight;
}

// ── Advisor reply bubble (renders **bold** + tool badges) ────────────────────
function addAdvisorBubble(text, tools, timing){
  const c=document.getElementById('chatMsgs');
  const row=document.createElement('div');
  row.className='msg-row';
  const wrap=document.createElement('div');
  wrap.className='msg-wrap';
  const b=document.createElement('div');
  b.className='bubble bot';
  b.innerHTML=esc(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  const meta=document.createElement('div');
  meta.className='msg-meta';
  meta.textContent=new Date().toLocaleTimeString();
  if(timing){const t=document.createElement('span');t.className='t-badge';t.textContent=timing;meta.appendChild(t);}
  if(tools&&tools.length){
    const ts=document.createElement('span');
    ts.innerHTML=tools.map(n=>`<span class="t-badge">${esc(n)}</span>`).join('');
    meta.appendChild(ts);
  }
  wrap.appendChild(b);wrap.appendChild(meta);
  row.appendChild(wrap);
  c.appendChild(row);
  c.scrollTop=c.scrollHeight;
}

// ── Trace panel ─────────────────────────────────────────────────────────────
const NODE_LABELS={router:'Router',onboarding:'Onboarding',existing_user_greeting:'Greeting'};
const NODE_COLORS={router:'nb-router',onboarding:'nb-onboarding',existing_user_greeting:'nb-existing_user_greeting'};

function renderTrace(trace){
  const el=document.getElementById('pane-trace');
  if(!trace.length){el.innerHTML='<div class="empty">No node trace captured.</div>';return;}
  el.innerHTML=trace.map((s,i)=>{
    const cls=NODE_COLORS[s.node]||'nb-default';
    const lbl=NODE_LABELS[s.node]||s.node;
    const keys=Object.keys(s.changes||{}).filter(k=>k!=='response_sent');
    return`<div class="node-card">
      <div class="nc-hdr">
        <span class="nc-idx">${i+1}</span>
        <span class="nbadge ${cls}">${lbl}</span>
        <span class="dur">⏱ ${s.duration_ms}ms</span>
      </div>
      ${keys.length?`<table class="ch-table">
        <tr><th>Field changed</th><th>New value</th></tr>
        ${keys.map(k=>`<tr><td>${esc(k)}</td><td class="${vcls(s.changes[k])}">${fmtV(s.changes[k])}</td></tr>`).join('')}
      </table>`:'<span style="color:#334155;font-size:12px;">No state changes</span>'}
    </div>`;
  }).join('');
}

function vcls(v){
  if(v===null||v===undefined)return 'v-null';
  if(v===true)return 'v-true';
  if(v===false)return 'v-false';
  if(typeof v==='number')return 'v-num';
  return '';
}
function fmtV(v){
  if(v===null||v===undefined)return 'null';
  if(typeof v==='boolean')return String(v);
  if(typeof v==='string')return trunc(v,180);
  if(typeof v==='object')return trunc(JSON.stringify(v),200);
  return String(v);
}
function trunc(s,n){return s.length>n?s.slice(0,n)+'…':s;}

// ── State panel ──────────────────────────────────────────────────────────────
function renderState(state){
  document.getElementById('pane-state').innerHTML=`<div class="jv">${jhl(state)}</div>`;
}

// ── Session panel ────────────────────────────────────────────────────────────
function renderSession(sess){
  const el=document.getElementById('sessContent');
  if(!sess){
    el.innerHTML='<div class="empty">No active Redis session.<br><small>User is either fully onboarded or hasn\'t started yet.</small></div>';
    return;
  }
  el.innerHTML=`<div class="jv">${jhl(sess)}</div>`;
}

async function refreshSess(){
  const waId=document.getElementById('waId').value.trim();
  try{
    const r=await fetch('/testing/session/'+encodeURIComponent(waId));
    const d=await r.json();
    renderSession(d.session);
  }catch(e){console.error(e);}
}

async function clearSess(){
  const waId=document.getElementById('waId').value.trim();
  if(!confirm('Reset Redis session for '+waId+'?\n\nThis will restart onboarding for this user.'))return;
  try{
    await fetch('/testing/session/'+encodeURIComponent(waId),{method:'DELETE'});
    document.getElementById('sessContent').innerHTML='<div style="color:#4ade80;font-size:13px;">✓ Session cleared — next message will trigger new user onboarding.</div>';
  }catch(e){console.error(e);}
}

// ── Messages panel ───────────────────────────────────────────────────────────
function renderMsgs(msgs){
  const el=document.getElementById('msgsContent');
  if(!msgs.length){el.innerHTML='<div class="empty">No messages in DB for this wa_id.</div>';return;}
  el.innerHTML=`<table class="mt">
    <thead><tr><th>Dir</th><th>Time</th><th>Message</th></tr></thead>
    <tbody>${msgs.map(m=>`<tr>
      <td><span class="${m.direction==='inbound'?'dir-in':'dir-out'}">${m.direction}</span></td>
      <td style="color:#475569;white-space:nowrap;font-size:11px;">${(m.created_at||'').replace('T',' ').slice(0,19)}</td>
      <td style="color:#e2e8f0;">${esc(trunc(m.message_text||'',120))}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

// ── User panel ───────────────────────────────────────────────────────────────
function renderUser(u){
  const el=document.getElementById('userContent');
  if(!u){
    el.innerHTML='<div class="empty">No DB user found for this wa_id.<br><small>User is either in onboarding or hasn\'t sent "Hi" yet.</small></div>';
    return;
  }
  const allerg=(u.allergies||[]).map(a=>a.allergen).filter(Boolean);
  const meds=(u.medical_conditions||[]).map(c=>c.condition_name).filter(Boolean);
  const diet=u.health_profile?.dietary_preference||'—';
  el.innerHTML=`
    <div class="prof-sect"><div class="plabel">Name</div><div class="pval">${esc(u.full_name||'—')}</div></div>
    <div class="prof-sect"><div class="plabel">WhatsApp ID</div><div class="pval" style="font-family:monospace;font-size:12px;color:#7dd3fc">${esc(u.whatsapp_user_id||'—')}</div></div>
    <div class="prof-sect"><div class="plabel">Dietary Preference</div><div class="pval">${esc(diet)}</div></div>
    <div class="prof-sect">
      <div class="plabel">Allergies (${allerg.length})</div>
      <div class="ptags">${allerg.length?allerg.map(a=>`<span class="tag">🚫 ${esc(a)}</span>`).join(''):'<span style="color:#334155">None</span>'}</div>
    </div>
    <div class="prof-sect">
      <div class="plabel">Regular Medicines (${meds.length})</div>
      <div class="ptags">${meds.length?meds.map(m=>`<span class="tag">💊 ${esc(m)}</span>`).join(''):'<span style="color:#334155">None</span>'}</div>
    </div>
    <div class="prof-sect"><div class="plabel">User ID</div><div class="pval" style="font-family:monospace;font-size:11px;color:#475569">${esc(u.id||'—')}</div></div>
    <div class="prof-sect"><div class="plabel">Created</div><div class="pval" style="font-size:12px;color:#64748b">${esc((u.created_at||'').replace('T',' ').slice(0,19))}</div></div>`;
}

// ── JSON syntax highlighter ──────────────────────────────────────────────────
function jhl(obj){
  const json=JSON.stringify(obj,null,2);
  return esc(json).replace(
    /(&quot;(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\&])*&quot;(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    m=>{
      if(/&quot;/.test(m)){
        if(/:$/.test(m))return`<span class="jk">${m}</span>`;
        return`<span class="js">${m}</span>`;
      }
      if(/true|false/.test(m))return`<span class="jb">${m}</span>`;
      if(/null/.test(m))return`<span class="jz">${m}</span>`;
      return`<span class="jn">${m}</span>`;
    }
  );
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

// ── Keyboard shortcut ────────────────────────────────────────────────────────
document.getElementById('msgInput').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}
});
</script>
</body>
</html>
"""
