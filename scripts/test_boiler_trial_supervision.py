"""Real HTTP fault injection: a delayed read must not delay trial keepalives."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
import urllib.request

from boiler_trial_supervision import TrialSupervision


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.acks = []
        self.withdrawals = []
        self.reject = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                time.sleep(1.2)  # Optional read longer than this fixture's lease.
                self.reply({"observed": True})

            def do_POST(self):
                now = time.monotonic()
                if owner.reject:
                    self.reply({"phase": "wrong_scope"})
                    return
                expired = bool(owner.acks) and now - owner.acks[-1] >= 1.0
                if not expired:
                    owner.acks.append(now)
                self.reply({"phase": "stopping" if expired else "heating"})

            def reply(self, value):
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = "http://127.0.0.1:" + str(self.server.server_address[1])

    def keepalive(self):
        request = urllib.request.Request(self.url + "/keepalive", data=b"{}", method="POST")
        with urllib.request.urlopen(request, timeout=.5) as response:
            return json.load(response)["phase"]

    def slow_read(self):
        with urllib.request.urlopen(self.url + "/telemetry", timeout=2) as response:
            return json.load(response)

    def test_serial_read_reproduces_the_observed_lease_loss(self):
        self.assertEqual(self.keepalive(), "heating")
        self.slow_read()
        self.assertEqual(self.keepalive(), "stopping")

    def test_independent_keepalives_survive_the_same_delayed_read(self):
        supervisor = TrialSupervision(self.keepalive, lambda: self.withdrawals.append(True),
                                      interval_seconds=.1, confirmation_limit_seconds=.8)
        supervisor.start()
        self.addCleanup(supervisor.stop)
        self.slow_read()
        self.assertGreaterEqual(len(self.acks), 5)
        self.assertLess(max(b - a for a, b in zip(self.acks, self.acks[1:])), 1.0)
        self.assertEqual(supervisor.last_phase, "heating")
        self.assertIsNone(supervisor.failure)
        self.assertEqual(self.withdrawals, [])

    def test_bad_scope_withdraws_once_and_never_continues_keepalives(self):
        withdrawn = threading.Event()
        self.reject = True
        supervisor = TrialSupervision(self.keepalive,
            lambda: (self.withdrawals.append(True), withdrawn.set()),
            interval_seconds=.05, confirmation_limit_seconds=.3)
        supervisor.start()
        self.addCleanup(supervisor.stop)
        self.assertTrue(withdrawn.wait(2))
        supervisor.stop()
        self.assertIsInstance(supervisor.failure, ValueError)
        self.assertEqual(self.withdrawals, [True])

    def test_lost_connection_withdraws_once(self):
        withdrawn = threading.Event()
        def missing():
            raise TimeoutError("Injected response loss")
        supervisor = TrialSupervision(missing,
            lambda: (self.withdrawals.append(True), withdrawn.set()),
            interval_seconds=.05, confirmation_limit_seconds=.2)
        supervisor.start()
        self.addCleanup(supervisor.stop)
        self.assertTrue(withdrawn.wait(2))
        supervisor.stop()
        self.assertIsInstance(supervisor.failure, TimeoutError)
        self.assertEqual(self.withdrawals, [True])

    def test_late_healthy_response_does_not_hide_an_unconfirmed_gap(self):
        withdrawn = threading.Event()
        def late():
            time.sleep(.25)
            return "heating"
        supervisor = TrialSupervision(late, withdrawn.set,
            interval_seconds=.05, confirmation_limit_seconds=.2)
        supervisor.start()
        self.addCleanup(supervisor.stop)
        self.assertTrue(withdrawn.wait(2))
        self.assertIsInstance(supervisor.failure, TimeoutError)

    def test_evidence_write_failure_cannot_suppress_withdrawal(self):
        withdrawn = threading.Event()
        def broken_report(event):
            raise OSError("Injected full disk")
        supervisor = TrialSupervision(lambda: "wrong_scope", withdrawn.set,
            report=broken_report, interval_seconds=.05, confirmation_limit_seconds=.2)
        supervisor.start()
        self.addCleanup(supervisor.stop)
        self.assertTrue(withdrawn.wait(2))
        self.assertIsInstance(supervisor.failure, ValueError)


if __name__ == "__main__":
    unittest.main()
