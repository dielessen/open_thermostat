"""Keep attended trial supervision independent of optional HTTP observations.

This module sends no device command by itself. The caller supplies the existing
scoped keepalive and withdrawal functions, including bounded request timeouts.
It cannot start heat, change a target, extend the firmware deadline or revive a
terminal session. The firmware's own five-second lease remains authoritative.
"""
import threading
import time


class TrialSupervision:
    active_phases = frozenset(("baseline", "ready", "heating"))
    terminal_phases = frozenset(("stopping", "completed", "fault", "closed"))

    def __init__(self, keepalive, withdraw, *, report=lambda event: None,
                 interval_seconds=1, confirmation_limit_seconds=4):
        if not 0 < interval_seconds < confirmation_limit_seconds:
            raise ValueError("Invalid supervision timing")
        self.keepalive = keepalive
        self.withdraw = withdraw
        self.report = report
        self.interval = interval_seconds
        self.limit = confirmation_limit_seconds
        self.finished = threading.Event()
        self.failure = None
        self.last_phase = None
        self.thread = threading.Thread(target=self._run, name="trial-supervision", daemon=True)

    def _report(self, event):
        try:
            self.report(event)
        except Exception:
            pass  # Evidence IO cannot suppress withdrawal.

    def start(self):
        self.thread.start()

    def stop(self):
        self.finished.set()
        self.thread.join(timeout=3)

    def _run(self):
        confirmed = time.monotonic()
        try:
            while not self.finished.is_set():
                if time.monotonic() - confirmed >= self.limit:
                    raise TimeoutError("Operator supervision was not confirmed in time")
                try:
                    phase = self.keepalive()
                except Exception as error:
                    self._report({"event": "keepalive_unconfirmed", "type": type(error).__name__})
                else:
                    if time.monotonic() - confirmed >= self.limit:
                        raise TimeoutError("Late response cannot confirm continuous supervision")
                    if phase in self.terminal_phases:
                        self.last_phase = phase
                        return
                    if phase not in self.active_phases:
                        raise ValueError("Unexpected trial scope or phase")
                    confirmed = time.monotonic()
                    self.last_phase = phase
                self.finished.wait(self.interval)
        except Exception as error:
            self.failure = error
            self._report({"event": "supervision_failed", "type": type(error).__name__})
            try:
                self.withdraw()
            except Exception as withdrawal_error:
                self._report({"event": "withdrawal_unconfirmed", "type": type(withdrawal_error).__name__})
        finally:
            self.finished.set()
