"""HTTP API for the live console.

    uvicorn dobaara.api:app --reload

Environment:
    RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET   rzp_test_ keys (optional; mock mode without them)
    RAZORPAY_WEBHOOK_SECRET                 required for /webhooks/razorpay
    ANTHROPIC_API_KEY                       optional; enables parser="llm" on replies
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .razorpay import verify_webhook_signature
from .service import Service

app = FastAPI(title="Dobaara", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_ledger = os.environ.get("DOBAARA_LEDGER")
service = Service(ledger_path=Path(_ledger) if _ledger else None)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    parser: str = Field(default="baseline", pattern="^(baseline|llm)$")


class AdvanceIn(BaseModel):
    hours: int = Field(ge=1, le=24 * 31)


class DemoIn(BaseModel):
    n: int = Field(default=6, ge=1, le=50)
    seed: int = 4242


@app.get("/health")
def health() -> dict:
    return {"ok": True, "razorpay_mode": service.razorpay.mode}


@app.get("/summary")
def summary() -> dict:
    return service.summary()


@app.post("/demo/cases")
def demo(body: DemoIn) -> dict:
    cases = service.open_demo_cases(body.n, body.seed)
    return {"opened": [c.case_id for c in cases]}


@app.get("/cases")
def cases() -> list[dict]:
    return [{k: v for k, v in service.case_view(cid).items() if k not in ("timeline", "curve")}
            for cid in service.cases]


@app.get("/cases/{case_id}")
def case(case_id: str) -> dict:
    if case_id not in service.cases:
        raise HTTPException(404, "no such case")
    return service.case_view(case_id)


@app.post("/cases/{case_id}/reply")
def reply(case_id: str, body: ReplyIn) -> dict:
    if case_id not in service.cases:
        raise HTTPException(404, "no such case")
    try:
        return service.reply(case_id, body.text, body.parser)
    except RuntimeError as e:  # LLM unavailable: say so rather than guess
        raise HTTPException(503, str(e))


@app.post("/cases/{case_id}/link-paid")
def link_paid(case_id: str) -> dict:
    if case_id not in service.cases:
        raise HTTPException(404, "no such case")
    service.mark_link_paid(case_id)
    return service.case_view(case_id)


@app.post("/clock/advance")
def advance(body: AdvanceIn) -> dict:
    return {"executed": service.advance(body.hours), "clock": service.clock.isoformat()}


@app.get("/outbox")
def outbox() -> list[dict]:
    return [{"case_id": m.case_id, "at": m.at.isoformat(), "kind": m.kind, "text": m.text, "link": m.link}
            for m in service.outbox[-200:]]


@app.get("/queue")
def queue() -> list[dict]:
    return service.queue


@app.get("/audit")
def audit(limit: int = 200) -> list[dict]:
    return service.engine.ledger.dump()[-limit:]


@app.post("/webhooks/razorpay")
async def webhook(request: Request, x_razorpay_signature: str = Header(default="")) -> dict:
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "RAZORPAY_WEBHOOK_SECRET is not set")
    body = await request.body()
    if not verify_webhook_signature(body, x_razorpay_signature, secret):
        raise HTTPException(401, "bad signature")
    return service.handle_webhook(json.loads(body))
