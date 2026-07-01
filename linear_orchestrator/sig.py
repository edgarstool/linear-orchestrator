"""Linear webhook signature + timestamp verification."""
from __future__ import annotations
import hmac
import hashlib
import json
import time
from typing import Tuple


def verify(body: bytes, secret: str, sig_header: str, ts_header: str,
           tolerance_sec: int = 300) -> Tuple[bool, str]:
    """Return (ok, reason). `secret` may be a single string OR a list/tuple/iterable
    of candidate secrets — useful because Linear sends both:
      1. workspace webhook (signed with LINEAR_WEBHOOK_SECRET)
      2. OAuth app webhook (signed with the OAuth app's separate signing secret)
    to the same URL. We try each and accept on first match.
    """
    if not sig_header:
        return False, "missing Linear-Signature"

    # Normalise candidates to a list of non-empty strings.
    if isinstance(secret, (list, tuple, set)):
        candidates = [s for s in secret if s]
    elif isinstance(secret, str) and secret:
        candidates = [secret]
    else:
        return False, "no secret configured"

    sig_lower = sig_header.strip().lower()
    matched_idx = -1
    for i, sec in enumerate(candidates):
        expected = hmac.new(sec.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig_lower, expected.lower()):
            matched_idx = i
            break
    if matched_idx < 0:
        return False, f"signature mismatch (tried {len(candidates)} secrets)"

    # timestamp: header OR webhookTimestamp field in body
    ts_value = ts_header
    if not ts_value:
        try:
            ts_value = str(json.loads(body.decode("utf-8")).get("webhookTimestamp", ""))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, "body not JSON; no timestamp header"

    try:
        ts_ms = int(ts_value)
    except (TypeError, ValueError):
        return False, "timestamp missing or invalid"

    ts_sec = ts_ms / 1000 if ts_ms > 10_000_000_000 else ts_ms
    if abs(time.time() - ts_sec) > tolerance_sec:
        return False, f"timestamp outside ±{tolerance_sec}s window"
    return True, f"ok (secret #{matched_idx + 1})"
