"""Same bounded original-send grant proof for explicitly negotiated sessions."""
from __future__ import annotations
import math
import re

_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
MAX_GRANT_PROOFS = 8


def register_grant_proof(proofs, nonce, sent):
    if (not isinstance(nonce, str) or not _ID.fullmatch(nonce)
            or type(sent) not in (int, float) or not math.isfinite(sent)):
        raise ValueError("invalid_grant_proof")
    # Exact retries must NOT replace the original send timestamp.
    proofs.setdefault(nonce, sent)
    while len(proofs) > MAX_GRANT_PROOFS:
        proofs.pop(next(iter(proofs)))


def consume_grant_proof(proofs, nonce, now, grant_seconds=10):
    """One-shot conservative deadline; NEVER receipt+grant or FW clock comparison.

    grant_seconds: the session's grant lifetime (graph sessions 10 s, the v1
    shadow session 30 s since beta.19).
    """
    if not isinstance(nonce, str) or not _ID.fullmatch(nonce):
        return None
    sent = proofs.pop(nonce, None)
    if (sent is None or type(now) not in (int, float) or not math.isfinite(now)
            or type(sent) not in (int, float) or not math.isfinite(sent)
            or not 0 <= now-sent < grant_seconds):
        return None
    return sent + grant_seconds
