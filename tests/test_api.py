import json

import pytest
from fastapi.testclient import TestClient

from dobaara import api
from dobaara.razorpay import LiveKeyRefused, RazorpayClient, sign_webhook, verify_webhook_signature
from dobaara.service import Service

SECRET = "whsec_test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api, "service", Service(razorpay=RazorpayClient()))
    return TestClient(api.app)


def failed_payment(pid="pay_T1", reason="insufficient_funds", amount=49900):
    return {"event": "payment.failed", "payload": {"payment": {"entity": {
        "id": pid, "amount": amount, "currency": "INR", "method": "upi", "recurring": True,
        "customer_id": "cust_1", "token_id": "token_1", "error_reason": reason,
        "error_description": "Payment failed", "notes": {}}}}}


def post_webhook(client, event, secret=SECRET):
    body = json.dumps(event).encode()
    return client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sign_webhook(body, secret)})


def test_live_keys_are_refused():
    with pytest.raises(LiveKeyRefused):
        RazorpayClient("rzp_live_abc", "secret")


def test_mock_mode_without_keys():
    assert RazorpayClient().mode == "mock"


def test_signature_roundtrip():
    assert verify_webhook_signature(b"{}", sign_webhook(b"{}", "s"), "s")
    assert not verify_webhook_signature(b"{}", sign_webhook(b"{}", "s"), "other")


def test_bad_signature_rejected(client):
    assert post_webhook(client, failed_payment(), secret="wrong").status_code == 401


def test_failed_recurring_payment_opens_a_case(client):
    r = post_webhook(client, failed_payment())
    assert r.status_code == 200 and r.json()["failure_class"] == "insufficient_funds"
    view = client.get("/cases/case_pay_T1").json()
    assert view["timeline"][0]["event"] == "case_opened"
    assert any(p["type"] == "payment_link" for p in view["pending"])


def test_duplicate_webhook_is_idempotent(client):
    post_webhook(client, failed_payment())
    post_webhook(client, failed_payment())
    assert len(client.get("/cases").json()) == 1


def test_one_time_payment_failures_are_ignored(client):
    ev = failed_payment()
    ev["payload"]["payment"]["entity"].update(recurring=False, token_id=None)
    assert post_webhook(client, ev).json() == {"ignored": "not a recurring debit"}


def test_reply_and_clock_flow(client):
    client.post("/demo/cases", json={"n": 3})
    cid = next(c["case_id"] for c in client.get("/cases").json() if not c["recovered"])
    r = client.post(f"/cases/{cid}/reply", json={"text": "band karo ye"})
    assert r.json()["intent"] == "cancel"
    client.post("/clock/advance", json={"hours": 24 * 30})
    view = client.get(f"/cases/{cid}").json()
    assert view["stopped"]
    reply_seq = next(e["seq"] for e in view["timeline"] if e["event"] == "reply_received")
    assert not any(e["event"] == "action_executed" and e["seq"] > reply_seq and e["data"]["type"] != "stop"
                   for e in view["timeline"])
    s = client.get("/summary").json()
    assert s["verifier"]["violations"] == 0 and s["verifier"]["chain_ok"]


def test_payment_link_paid_webhook_recovers(client):
    post_webhook(client, failed_payment("pay_T2"))
    client.post("/clock/advance", json={"hours": 6})
    ev = {"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"reference_id": "case_pay_T2"}}}}
    assert post_webhook(client, ev).json()["recovered"]
    assert client.get("/cases/case_pay_T2").json()["recovered"]


def test_demo_runs_a_month_with_zero_violations(client):
    client.post("/demo/cases", json={"n": 20, "seed": 7})
    client.post("/clock/advance", json={"hours": 24 * 31})
    s = client.get("/summary").json()
    assert s["cases"] == 20 and s["verifier"]["violations"] == 0
    assert s["recovered"] >= 1


def test_ledger_stays_chronological_across_demo_cases(client):
    client.post("/demo/cases", json={"n": 8, "seed": 5085})
    cid = client.get("/cases").json()[0]["case_id"]
    client.post(f"/cases/{cid}/reply", json={"text": "salary 5 tarik ko aayegi, tab kar dunga"})
    client.post("/clock/advance", json={"hours": 24 * 20})
    ats = [r["at"] for r in client.get("/audit?limit=10000").json()]
    assert ats == sorted(ats)
