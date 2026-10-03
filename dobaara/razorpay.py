"""Razorpay adapter: test mode or mock, never live.

- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` set to `rzp_test_...` keys -> real calls to Razorpay's
  test environment (payment links, orders, recurring charges).
- No keys -> mock mode: same return shapes, deterministic ids, no network.
- A `rzp_live_` key is refused at construction. Moving real money is out of scope for a prototype.

Webhook signatures are verified with HMAC-SHA256 over the raw body, as Razorpay documents.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

API = "https://api.razorpay.com/v1"


class LiveKeyRefused(RuntimeError):
    pass


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def sign_webhook(body: bytes, secret: str) -> str:
    """Used by the demo and tests to produce a valid signature."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@dataclass
class RazorpayClient:
    key_id: str | None = None
    key_secret: str | None = None
    timeout: float = 15.0
    calls: list[dict[str, Any]] = field(default_factory=list)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    def __post_init__(self) -> None:
        if self.key_id and self.key_id.startswith("rzp_live_"):
            raise LiveKeyRefused("Dobaara only runs against Razorpay test mode. Use an rzp_test_ key.")
        if self.key_id and not self.key_id.startswith("rzp_test_"):
            raise ValueError("RAZORPAY_KEY_ID must be an rzp_test_ key")

    @classmethod
    def from_env(cls) -> "RazorpayClient":
        return cls(os.environ.get("RAZORPAY_KEY_ID") or None, os.environ.get("RAZORPAY_KEY_SECRET") or None)

    @property
    def mode(self) -> str:
        return "test" if self.key_id and self.key_secret else "mock"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"method": "POST", "path": path, "payload": payload, "mode": self.mode})
        if self.mode == "mock":
            return self._mock(path, payload)
        resp = httpx.post(f"{API}{path}", json=payload, auth=(self.key_id, self.key_secret), timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"Razorpay {path} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def _mock(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        n = next(self._ids)
        if path == "/payment_links":
            pid = f"plink_mock{n:06d}"
            return {"id": pid, "short_url": f"https://rzp.io/i/mock{n:06d}", "status": "created",
                    "amount": payload["amount"], "reference_id": payload.get("reference_id")}
        if path == "/orders":
            return {"id": f"order_mock{n:06d}", "amount": payload["amount"], "status": "created"}
        if path == "/payments/create/recurring":
            return {"razorpay_payment_id": f"pay_mock{n:06d}", "razorpay_order_id": payload["order_id"]}
        return {"id": f"mock{n:06d}"}

    # -- operations Dobaara performs ------------------------------------------------------------------

    def create_payment_link(self, *, amount_inr: float, reference_id: str, description: str,
                            customer_name: str, contact: str, expire_in_days: int = 7) -> dict[str, Any]:
        return self._post("/payment_links", {
            "amount": int(round(amount_inr * 100)),
            "currency": "INR",
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description,
            "expire_by": int(time.time()) + expire_in_days * 86400,
            "customer": {"name": customer_name, "contact": contact},
            # Dobaara sends its own messages so the contact-hours and outreach-cap rules hold.
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {"source": "dobaara", "case": reference_id},
        })

    def charge_recurring(self, *, amount_inr: float, customer_id: str, token: str, email: str, contact: str,
                         case_id: str) -> dict[str, Any]:
        """Subsequent recurring debit on an existing mandate: create an order, then charge the token."""
        paise = int(round(amount_inr * 100))
        order = self._post("/orders", {"amount": paise, "currency": "INR", "payment_capture": 1,
                                       "receipt": case_id, "notes": {"source": "dobaara"}})
        return self._post("/payments/create/recurring", {
            "email": email, "contact": contact, "amount": paise, "currency": "INR", "order_id": order["id"],
            "customer_id": customer_id, "token": token, "recurring": "1",
            "description": f"Dobaara retry for {case_id}", "notes": {"source": "dobaara", "case": case_id},
        })
