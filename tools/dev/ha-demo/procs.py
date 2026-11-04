"""Child processes of the demo: each in its own process group, its output in a log file, all stopped at the end."""
import os
import signal
import subprocess
import time


class Processes:
    def __init__(self, logdir):
        self.logdir = logdir
        self.children = []  # (name, Popen, log file)

    def start(self, name, argv, env=None, cwd=None):
        log = open(os.path.join(self.logdir, name + ".log"), "ab")
        proc = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                env=env, cwd=cwd, start_new_session=True)
        self.children.append((name, proc, log))
        return proc

    def alive(self, name):
        return any(n == name and p.poll() is None for n, p, _ in self.children)

    def stop(self, name, timeout=60):
        """SIGTERM to the process group, SIGKILL after the timeout."""
        for n, proc, log in list(self.children):
            if n != name:
                continue
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(10)
            log.close()
            self.children.remove((n, proc, log))

    def stop_all(self):
        for name, _, _ in reversed(list(self.children)):
            self.stop(name, timeout=30)


def wait_port(host, port, timeout=30):
    import socket
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with socket.socket() as s:
            s.settimeout(1)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False
