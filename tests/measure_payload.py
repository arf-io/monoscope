"""Drive the real panel in a pty for N seconds and report payload statistics."""
import os, sys, re, time, statistics, tempfile
sys.path.insert(0, 'tests')
import test_monoscope_pty as T

TAG = os.environ.get("TAG", "?")
SECS = float(os.environ.get("SECS", "8"))
timing = tempfile.mktemp(suffix=".timing")

c = T.MonoscopePtyCase('test_bench_draws_at_200x60_and_100x30')
c.setUp()
c.env["MONOSCOPE_MOTION"] = "full"     # worst case: ambient colour motion
c.env["MONOSCOPE_TIMING"] = timing
c.env["MONOSCOPE_FPS"] = "8"
p = T.PtyPanel(60, 200, c.env)
c.panel = p
p.wait_for("BRIGHTNESS", timeout=10)
end = time.time() + SECS
while time.time() < end:
    p.drain(quiet=0.05, timeout=0.3)
p.send("q"); p.drain(timeout=1.0)
try: p.proc.wait(timeout=5)
except Exception: pass
c.tearDown()

sizes = [int(m) for m in re.findall(r"bytes=(\d+)", open(timing).read())]
sizes = [s for s in sizes if s > 0]
os.unlink(timing)
if not sizes:
    print(TAG, "no frames recorded"); sys.exit(1)
sizes.sort()
print("%-9s frames=%-4d  max=%-7d p95=%-7d median=%-6d total=%d" % (
    TAG, len(sizes), sizes[-1], sizes[int(len(sizes)*0.95)-1],
    sizes[len(sizes)//2], sum(sizes)))
