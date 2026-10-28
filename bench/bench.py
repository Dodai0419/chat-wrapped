"""python bench/bench.py: parse the demo export, search it (whatsapp-mcp's query rules), build the six cards. Median of 5."""
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import chat_wrapped as cw  # noqa: E402

text = (ROOT / "examples" / "maya-and-leo.txt").read_text(encoding="utf-8")
msgs = cw.parse(text)
QUERIES = ["flight*", '"booked for thursday"', "CAFE", "nothing here at all"]


def med(fn):
    runs = []
    for _ in range(5):
        t = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t)
    return statistics.median(runs) * 1000


print(f"parse {len(msgs):,} messages:            {med(lambda: cw.parse(text)):7.1f} ms")
print(f"search 4 queries, limit 30:        {med(lambda: cw.search(msgs, QUERIES, limit=30)):7.1f} ms")
print(f"search 4 queries, no limit:        {med(lambda: cw.search(msgs, QUERIES, limit=10**9)):7.1f} ms")
print(f"stats + six cards (HTML):          {med(lambda: cw.page(cw.stats(msgs), 'Maya & Leo')):7.1f} ms")
