"""Bounded connection-owner diagnostics, never source or actuator evidence.

Counts callback/worker observations only, not broker-wide or per-device traffic.
No clocks, identifiers, payloads, persistence, tasks or automatic reset on reads.
"""
MAX_COUNT = 2**31 - 1
LANES = ("temperature", "tv02")
OUTCOMES = ("callback", "enqueued", "dropped_closed", "dropped_busy",
    "dropped_retained", "dropped_payload", "dropped_queue_full", "dropped_timestamp",
    "worker_accepted", "worker_rejected", "worker_error")


class OriginalIngressDiagnostics:
    def __init__(self):
        self._counts = {lane: dict.fromkeys(OUTCOMES, 0) for lane in LANES}
        self._saturated = dict.fromkeys(LANES, False)
        self._unrouted = 0
        self._unrouted_saturated = False

    def record(self, lane, outcome):
        # Invalid labels cannot allocate new buckets or disrupt optional receive.
        if type(lane) is not str or type(outcome) is not str:
            return False
        if lane not in self._counts or outcome not in self._counts[lane]:
            return False
        count = self._counts[lane][outcome]
        if count < MAX_COUNT:
            self._counts[lane][outcome] = count + 1
        else:
            self._saturated[lane] = True
        return True

    def unrouted(self):
        if self._unrouted < MAX_COUNT:
            self._unrouted += 1
        else:
            self._unrouted_saturated = True

    def snapshot(self):
        return {"scope": "connection_owner_lifetime_original_ingress",
            "persistent": False, "control_qualified": False,
            "per_device": False, "unrouted_callbacks": self._unrouted,
            "unrouted_saturated": self._unrouted_saturated,
            "lanes": {lane: {"counts": dict(counts), "saturated": self._saturated[lane]}
                for lane, counts in self._counts.items()}}
