import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import chat_wrapped as cw  # noqa: E402

T0 = datetime(2026, 3, 1, 10, 0)
MSGS = [  # whatsapp-mcp test/store.test.mts search fixture (67b6c5e), as exported messages
    {"id": "s1", "ts": T0.replace(minute=1), "sender": "Gilad Shoham", "body": "The flights are booked for Thursday", "media": False},
    {"id": "s2", "ts": T0.replace(minute=2), "sender": "Gilad Shoham", "body": "Lease signed, deposit paid", "media": False},
    {"id": "s3", "ts": T0.replace(minute=3), "sender": "Stranger One", "body": "Café on Thursday? the flight lands late", "media": False},
    {"id": "s4", "ts": T0.replace(minute=4), "sender": "Stranger Two", "body": "שלום, מה שלומך? נתראה ביום חמישי", "media": False},
    {"id": "s5", "ts": T0.replace(minute=5), "sender": "Gilad Shoham", "body": "release notes attached", "media": False},
]


def ids(q, **kw):
    return ",".join(m["id"] for m in cw.search(MSGS, [q], limit=kw.pop("limit", 10), **kw)[0])


class Search(unittest.TestCase):
    """The search checks of whatsapp-mcp's own test file, same inputs and expected answers."""

    def test_upstream_cases(self):
        self.assertEqual(ids("flights"), "s1")
        self.assertEqual(ids("lease"), "s2")  # words match whole, so lease is not release
        self.assertEqual(ids("CAFE"), "s3")  # case and accents are ignored
        self.assertEqual(ids("thursday flight"), "s3")  # several words must all appear
        self.assertEqual(ids('"booked for thursday"'), "s1")
        self.assertEqual(ids('"thursday booked"'), "")
        self.assertEqual(ids("flight*"), "s3,s1")  # a trailing star matches word starts
        self.assertEqual(ids("שלומך"), "s4")
        self.assertEqual(ids("thursday"), "s3,s1")  # newest first
        self.assertEqual(ids("thursday", sender="gilad"), "s1")  # upstream narrows by chat; an export is one chat, so by sender
        self.assertEqual(ids("thursday", since=T0.replace(minute=2)), "s3")
        self.assertEqual(ids("!!!", limit=5), "")

    def test_batch_in_order_and_limit(self):
        got = cw.search(MSGS, ["flights", "lease", "nothing here", "שלום"], limit=10)
        self.assertEqual("|".join(",".join(m["id"] for m in h) for h in got), "s1|s2||s4")
        self.assertEqual(len(cw.search(MSGS, ["thursday"], limit=1)[0]), 1)

    def test_query_parsing(self):
        self.assertEqual(cw.parse_query('a "b c" d*'), [{"tokens": ["a"], "prefix": False}, {"tokens": ["b", "c"], "prefix": False},
                                                        {"tokens": ["d"], "prefix": True}])


class Export(unittest.TestCase):
    def test_ios_and_android_formats(self):
        ios = "[21/03/2026, 21:14:05] Maya: hi\nsecond line\n[22/03/2026, 08:00:00] Leo: ‎image omitted\n"
        a = cw.parse(ios)
        self.assertEqual([(m["ts"], m["sender"], m["body"], m["media"]) for m in a],
                         [(datetime(2026, 3, 21, 21, 14, 5), "Maya", "hi\nsecond line", False), (datetime(2026, 3, 22, 8, 0), "Leo", "image omitted", True)])
        android = "1/1/26, 12:00 AM - Messages and calls are end-to-end encrypted.\n3/21/26, 9:14 PM - Ana: hey\n3/22/26, 12:05 PM - Ben: <Media omitted>\n"
        b = cw.parse(android)
        self.assertEqual([(m["ts"], m["sender"], m["media"]) for m in b], [(datetime(2026, 3, 21, 21, 14), "Ana", False), (datetime(2026, 3, 22, 12, 5), "Ben", True)])
        self.assertEqual(cw.parse("01/02/2026, 10:00 - X: y", "mdy")[0]["ts"].month, 1)
        self.assertEqual(cw.parse("01/02/2026, 10:00 - X: y", "dmy")[0]["ts"].month, 2)

    def test_demo_numbers(self):
        msgs = cw.parse((ROOT / "examples" / "maya-and-leo.txt").read_text(encoding="utf-8"))
        s = cw.stats(msgs)
        self.assertEqual(s["messages"], 4261)
        self.assertEqual(dict(s["who"]), {"Maya": 2545, "Leo": 1716})
        self.assertEqual(msgs[-1]["body"], "happy new year!! 🎆\nsee you in 2027")
        self.assertGreaterEqual(s["streak"][0], 2)
        self.assertEqual((s["streak"][2] - s["streak"][1]).days + 1, s["streak"][0])


class Page(unittest.TestCase):
    def test_real_text_stays_in_the_page(self):
        s = cw.stats(cw.parse("[01/01/2026, 10:00:00] A <b>: hello & bye\n"))
        p = cw.page(s, "A & <B>")
        self.assertIn("A &amp; &lt;B&gt;", p)
        self.assertNotIn("<b>:", p)
        self.assertEqual(p.count('class="card"'), 6)
        self.assertIn("aria-hidden", p)  # the scramble layer is hidden from screen readers
        self.assertIn("prefers-reduced-motion", p)

    def test_cli_without_utf8_mode(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(ROOT / "chat_wrapped.py"), "--demo", "-o", d], capture_output=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            self.assertIn("4,261 messages", r.stdout.decode("utf-8"))
            self.assertTrue(Path(d, "wrapped.html").exists())
        r = subprocess.run([sys.executable, str(ROOT / "chat_wrapped.py"), "--demo", "--search", "happy new year"], capture_output=True, env=env)
        self.assertIn("happy new year!! 🎆", r.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
