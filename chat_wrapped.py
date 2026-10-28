#!/usr/bin/env python3
"""chat-wrapped: turn a WhatsApp chat export into a year-in-review story you can share, and search it.

    python chat_wrapped.py chat.txt -o out          # out/wrapped.html: 6 story cards that decode in
    python chat_wrapped.py chat.txt -o out --png    # also out/card-1.png ... card-6.png and out/wrapped.png
    python chat_wrapped.py chat.txt --search "flight*" '"booked for thursday"' --since 2026-03-01
    python chat_wrapped.py --demo -o out            # the bundled made-up chat

Search follows whatsapp-mcp (finereli/whatsapp-mcp, MIT): whole words, case and accents ignored, all words
must appear, "quoted phrases" in order, a trailing * for word starts, newest first. The cards decode in the
way ascii-reveal (quanhoangindex/ascii-reveal, MIT) does: a wave from the centre, each character running
through a density ramp and scrambled glyphs before it settles, the real text always in the page.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------- reading an export
# iOS: "[21/03/2026, 21:14:05] Maya: hi"   Android: "21/03/2026, 21:14 - Maya: hi" (also 12-hour times, dots, dashes)
HEAD = re.compile(r"^\u200e?\[?(\d{1,4})[./-](\d{1,2})[./-](\d{1,4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp]\.?\s?[Mm]\.?)?\]?\s*(?:-\s*)?(.*)$")
MEDIA = re.compile(r"^\u200e?(<Media omitted>|(image|video|audio|sticker|GIF|document) omitted|<attached: .*>)$", re.I)


def parse(text, order=None):
    """messages [{ts, sender, body, media}] from an export; order is 'dmy' or 'mdy' (guessed when None)"""
    rows = []
    for line in text.replace("\r\n", "\n").split("\n"):
        m = HEAD.match(line)
        if m and ": " in m.group(8):
            rows.append([m.groups(), *m.group(8).split(": ", 1)])
        elif m:
            rows.append([m.groups(), None, m.group(8)])  # a system line ("Messages are end-to-end encrypted", ...)
        elif rows:
            rows[-1][2] += "\n" + line  # a message that runs over several lines
    if order is None:  # a first field above 12 means day first; a second above 12 means month first
        firsts = [int(g[0]) for g, _, _ in rows if len(g[0]) <= 2]
        order = "mdy" if not any(f > 12 for f in firsts) and any(int(g[1]) > 12 for g, _, _ in rows) else "dmy"
    out = []
    for g, sender, body in rows:
        if sender is None:
            continue
        a, b, c = int(g[0]), int(g[1]), int(g[2])
        y, mo, d = (a, b, c) if len(g[0]) == 4 else (c, b, a) if order == "dmy" else (c, a, b)
        y += 2000 if y < 100 else 0
        h = int(g[3]) % 12 + (12 if g[6] and g[6][0] in "Pp" else 0) if g[6] else int(g[3])
        body = body.strip().lstrip("\u200e")
        out.append({"ts": datetime(y, mo, d, h, int(g[4]), int(g[5] or 0)), "sender": sender.strip().lstrip("\u200e~ "), "body": body,
                    "media": bool(MEDIA.match(body))})
    return out


# ---------------------------------------------------------------- search (whatsapp-mcp src/store.ts)
def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.category(c).startswith("M")).lower()


def words(s):
    return re.findall(r"[^\W_]+", fold(s))


def parse_query(q):
    """plain words are AND-ed, "quoted phrases" must appear in order, word* matches word starts"""
    out = []
    for raw in re.findall(r'"[^"]*"|\S+', q):
        quoted = raw.startswith('"')
        tokens = words(raw.replace('"', "") if quoted else raw)
        if tokens:
            out.append({"tokens": tokens, "prefix": not quoted and raw.endswith("*")})
    return out


def _has(have, t):
    n = len(t["tokens"])
    for i in range(len(have) - n + 1):
        if all(have[i + j].startswith(tok) if j == n - 1 and t["prefix"] else have[i + j] == tok for j, tok in enumerate(t["tokens"])):
            return True
    return False


def matches(text, terms):
    flat = fold(text)
    if not all(tok in flat for t in terms for tok in t["tokens"]):  # cheap substring check first, as upstream
        return False
    have = re.findall(r"[^\W_]+", flat)
    return all(_has(have, t) for t in terms)


def search(msgs, queries, sender=None, since=None, until=None, limit=30):
    """newest first, one list of hits per query; stops once every query has `limit` hits"""
    wants = [(parse_query(q), []) for q in queries]
    live = [w for w in wants if w[0]]
    for m in sorted(msgs, key=lambda m: m["ts"], reverse=True):
        if not live:
            break
        if (sender and fold(sender) not in fold(m["sender"])) or (since and m["ts"] < since) or (until and m["ts"] > until):
            continue
        for w in list(live):
            if matches(m["body"], w[0]):
                w[1].append(m)
                if len(w[1]) >= limit:
                    live.remove(w)
    return [w[1] for w in wants]


# ---------------------------------------------------------------- the year in numbers
STOP = set("the and you that for are with this have not but just was what your all can its it's i'm get got how out too yes yeah ok okay "
           "will one about from they there then them she him her his our has had did don't dont see now its lol haha".split())


def emoji(s):
    return [c for c in s if 0x1F300 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF]


def stats(msgs):
    real = [m for m in msgs if m["body"]]
    days = sorted({m["ts"].date() for m in real})
    best, run = (1, days[0], days[0]) if days else (0, None, None), 1
    for a, b in zip(days, days[1:]):
        run = run + 1 if b - a == timedelta(days=1) else 1
        if run > best[0]:
            best = (run, b - timedelta(days=run - 1), b)
    who = Counter(m["sender"] for m in real)
    replies = Counter()  # who answers first after a quiet night (6 h or more)
    for a, b in zip(real, real[1:]):
        if b["ts"] - a["ts"] >= timedelta(hours=6):
            replies[b["sender"]] += 1
    text = [m for m in real if not m["media"]]
    return {
        "first": real[0]["ts"].date() if real else None, "last": real[-1]["ts"].date() if real else None, "messages": len(real),
        "days": len(days), "who": who.most_common(), "hours": Counter(m["ts"].hour for m in real),
        "weekday": Counter(m["ts"].strftime("%A") for m in real).most_common(1), "media": sum(m["media"] for m in real),
        "words": Counter(w for m in text for w in words(m["body"]) if len(w) > 2 and w not in STOP and not w.isdigit()).most_common(5),
        "emoji": Counter(e for m in text for e in emoji(m["body"])).most_common(5), "streak": best, "starter": replies.most_common(1),
        "busiest": Counter(m["ts"].date() for m in real).most_common(1),
    }


# ---------------------------------------------------------------- the story
COLORS = ["#ff5e7e", "#7b61ff", "#00b3a4", "#ffb020", "#2f80ed", "#e2557f"]
REVEAL_JS = """
(() => {  // the decode preset of ascii-reveal: ramp, then scramble, then the real character; one shared loop at ~30 fps
  const RAMP = ' .:-=+*#%@', SCR = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+=?/', TICK = 60, VEL = 3.2, MAX_WAVE = 220;
  const still = /[?&]still=1/.test(location.search), calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cards = [...document.querySelectorAll('.card')];
  if (still) return;
  if (calm) { cards.forEach(c => c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease-out' })); return; }
  const hash = (a, b) => { let h = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b, 0xc2b2ae35); h ^= h >>> 13; return (h >>> 0) / 4294967296; };
  const runs = [];
  cards.forEach(card => {
    const r = card.getBoundingClientRect(), ox = r.left + r.width / 2, oy = r.top + r.height / 2;
    card.querySelectorAll('[data-r]').forEach((el, k) => {
      const text = el.textContent, e = el.getBoundingClientRect();
      const offset = Math.min(Math.hypot(e.left + e.width / 2 - ox, e.top + e.height / 2 - oy) / VEL, MAX_WAVE);
      const spread = Math.min(200, 40 + text.length * 4);
      const layer = document.createElement('span');
      layer.className = 'layer'; layer.setAttribute('aria-hidden', 'true');
      el.classList.add('decoding'); el.appendChild(layer);  // the real text stays in the DOM for readers and search
      runs.push({ el, layer, text, chars: [...text].map((c, i) => ({ c, at: offset + spread * i / Math.max(1, text.length), dur: 90 + 110 * hash(k, i) })) });
    });
  });
  const t0 = performance.now(); let last = 0;
  const frame = now => {
    const t = now - t0;
    if (now - last >= 30) {
      last = now;
      let busy = false;
      for (const run of runs) {
        if (run.done) continue;
        let s = '', open = false;
        run.chars.forEach((ch, i) => {
          const p = (t - ch.at) / ch.dur;
          if (ch.c === ' ' || ch.c === '\\n' || p >= 1) s += ch.c;
          else if (p < 0) { s += ' '; open = true; }
          else if (p < 0.35) { s += RAMP[1 + Math.floor(p / 0.35 * (RAMP.length - 1))]; open = true; }
          else { s += SCR[Math.floor(hash(i, Math.floor(t / TICK)) * SCR.length)]; open = true; }
        });
        run.layer.textContent = s;
        if (!open) { run.done = true; run.layer.remove(); run.el.classList.remove('decoding'); } else busy = true;
      }
      if (!busy) return;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
})();
"""


def _bar(pairs, color):
    top = max([v for _, v in pairs] or [1])
    return "".join(f'<div class="row"><span data-r>{html.escape(str(k))}</span><i style="width:{8 + 82 * v / top:.0f}%;background:{color}"></i>'
                   f'<b data-r>{v:,}</b></div>' for k, v in pairs)


def cards(s, title):
    e = html.escape
    fmt = lambda d: f"{d:%b} {d.day}, {d.year}" if d else "-"
    total = max(1, s["messages"])
    split = " ".join(f'<i style="flex:{n};background:{COLORS[i % 6]}"></i>' for i, (_, n) in enumerate(s["who"][:6]))
    hours = s["hours"]
    peak = max(range(24), key=lambda h: hours[h]) if s["messages"] else 0
    clock = "".join(f'<i style="height:{6 + 94 * hours[h] / max(1, hours[peak]):.0f}%{";background:#fff" if h == peak else ""}"></i>' for h in range(24))
    n, a, b = s["streak"]
    starter = s["starter"][0][0] if s["starter"] else "-"
    busy_day, busy_n = s["busiest"][0] if s["busiest"] else (None, 0)
    return [
        ("Your year together", f'<h2 data-r>{e(title)}</h2><p class="big" data-r>{s["messages"]:,}</p><p data-r>messages on {s["days"]} days</p>'
                               f'<p class="small" data-r>{fmt(s["first"])} to {fmt(s["last"])}</p>'),
        ("Who talks most", f'<div class="split">{split}</div>' + "".join(
            f'<p class="who"><i style="background:{COLORS[i % 6]}"></i><span data-r>{e(name)}</span><b data-r>{100 * c / total:.0f}%</b></p>'
            for i, (name, c) in enumerate(s["who"][:6]))),
        ("When you talk", f'<p class="big" data-r>{peak:02d}:00</p><p data-r>is your hour. {e(s["weekday"][0][0] if s["weekday"] else "-")}s are your day.</p>'
                          f'<div class="clock">{clock}</div><p class="small" data-r>busiest day: {fmt(busy_day)}, {busy_n} messages</p>'),
        ("Your words", _bar(s["words"], "#ffffff") + f'<p class="emo" data-r>{" ".join(c for c, _ in s["emoji"]) or "no emoji"}</p>'),
        ("Longest streak", f'<p class="big" data-r>{n} days</p><p data-r>in a row, {fmt(a)} to {fmt(b)}</p>'
                           f'<p class="small" data-r>{s["media"]:,} photos, videos and voice notes</p>'),
        ("Who breaks the silence", f'<p class="big" data-r>{e(starter)}</p><p data-r>writes first after a quiet night most often</p>'
                                   f'<p class="small" data-r>made with chat-wrapped</p>'),
    ]


CSS = """*{box-sizing:border-box;margin:0}body{background:#111;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:#fff}
.deck{display:flex;flex-wrap:wrap;gap:24px;padding:24px;justify-content:center}
.card{width:360px;height:640px;border-radius:28px;padding:40px 32px;display:flex;flex-direction:column;justify-content:center;gap:14px;position:relative;overflow:hidden}
.card h1{font-size:15px;letter-spacing:.14em;text-transform:uppercase;opacity:.8;position:absolute;top:34px;left:32px}
.card h2{font-size:30px;line-height:1.1}.card p{font-size:19px;line-height:1.35}.card .big{font-size:64px;font-weight:800;line-height:1}.card .small{font-size:14px;opacity:.8}
.split{display:flex;height:22px;border-radius:11px;overflow:hidden;gap:2px;margin-bottom:12px}.who{display:flex;align-items:center;gap:10px}
.who i{width:14px;height:14px;border-radius:7px}.who b{margin-left:auto}
.clock{display:flex;align-items:flex-end;gap:3px;height:120px}.clock i{flex:1;background:rgba(255,255,255,.45);border-radius:3px 3px 0 0}
.row{display:grid;grid-template-columns:110px 1fr 46px;align-items:center;gap:10px;font-size:18px}.row i{height:16px;border-radius:8px;opacity:.85}.row b{text-align:right}
.card .emo{font-size:30px;letter-spacing:.06em}
[data-r]{position:relative;white-space:pre-wrap}.decoding{color:transparent}.layer{position:absolute;inset:0;color:#fff;white-space:pre-wrap;font-family:ui-monospace,Consolas,monospace}
@media (prefers-reduced-motion: reduce){.layer{display:none}.decoding{color:inherit}}"""
BG = ["linear-gradient(160deg,#ff5e7e,#7b2ff7)", "linear-gradient(160deg,#7b61ff,#1f1c5a)", "linear-gradient(160deg,#00b3a4,#0b3d5c)",
      "linear-gradient(160deg,#ffb020,#e2557f)", "linear-gradient(160deg,#2f80ed,#0f1f4a)", "linear-gradient(160deg,#e2557f,#3a0f3f)"]


def page(s, title, only=None):
    deck = "".join(f'<section class="card" style="background:{BG[i]}"><h1>{h}</h1>{body}</section>'
                   for i, (h, body) in enumerate(cards(s, title)) if only is None or i == only)
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}: wrapped</title><style>{CSS}</style><main class="deck">{deck}</main><script>{REVEAL_JS}</script></html>')


# ---------------------------------------------------------------- cli
def find_chrome():
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        if p := shutil.which(name):
            return p
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if Path(p).exists():
            return p
    return None


def shot(chrome, html_path, png_path, size):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([chrome, "--headless=new", f"--user-data-dir={d}", "--hide-scrollbars", "--force-device-scale-factor=2",
                        f"--window-size={size[0]},{size[1]}", f"--screenshot={Path(png_path).resolve()}", Path(html_path).resolve().as_uri() + "?still=1"],
                       capture_output=True, timeout=120)
    return Path(png_path).exists()


def day(s):
    return datetime.strptime(s, "%Y-%m-%d")


def main(argv=None):
    for f in (sys.stdout, sys.stderr):
        f.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Turn a WhatsApp chat export into a year-in-review story you can share, and search it.")
    ap.add_argument("chat", nargs="?", help="the .txt from WhatsApp > chat > More > Export chat (without media)")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--title", help="name on the first card (default: the file name)")
    ap.add_argument("--year", type=int, help="only this calendar year")
    ap.add_argument("--dates", choices=["dmy", "mdy"], help="date order in the export (guessed when left out)")
    ap.add_argument("--png", action="store_true", help="also write card PNGs (needs Chrome or Edge)")
    ap.add_argument("--search", nargs="+", metavar="QUERY", help="search instead: words, \"phrases\", word*")
    ap.add_argument("--sender", help="with --search: only messages from this person (name fragment)")
    ap.add_argument("--since", type=day, help="with --search: YYYY-MM-DD")
    ap.add_argument("--until", type=day, help="with --search: YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--json", action="store_true", help="with --search: JSON lines")
    ap.add_argument("--demo", action="store_true", help="use the bundled made-up chat")
    a = ap.parse_args(argv)
    src = Path(__file__).with_name("examples") / "maya-and-leo.txt" if a.demo else Path(a.chat) if a.chat else None
    if not src:
        ap.error("give an exported chat .txt, or --demo")
    msgs = parse(src.read_text(encoding="utf-8-sig", errors="replace"), a.dates)
    if a.year:
        msgs = [m for m in msgs if m["ts"].year == a.year]
    if not msgs:
        print(f"chat-wrapped: no messages found in {src}", file=sys.stderr)
        return 1
    if a.search:
        for q, hits in zip(a.search, search(msgs, a.search, a.sender, a.since, a.until, a.limit)):
            if len(a.search) > 1 and not a.json:
                print(f"## {q} ({len(hits)} match{'' if len(hits) == 1 else 'es'})")
            for m in hits:
                print(json.dumps({"query": q, "ts": m["ts"].isoformat(), "sender": m["sender"], "body": m["body"]}, ensure_ascii=False) if a.json
                      else f"[{m['ts']:%Y-%m-%d %H:%M}] {m['sender']}: {m['body']}")
            if not hits and not a.json:
                print("No matches.")
        return 0
    s = stats(msgs)
    title = a.title or ("Maya & Leo" if a.demo else src.stem)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "wrapped.html").write_text(page(s, title), encoding="utf-8")
    people = ", ".join(f"{n} {c}" for n, c in s["who"][:4])
    print(f"chat-wrapped: {s['messages']:,} messages on {s['days']} days ({people}); longest streak {s['streak'][0]} days -> {out / 'wrapped.html'}")
    if a.png:
        chrome = find_chrome()
        if not chrome:
            print("chat-wrapped: --png needs Chrome or Edge", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as d:
            for i in range(6):
                one = Path(d, f"c{i}.html")
                one.write_text(page(s, title, only=i).replace(".deck{display:flex;flex-wrap:wrap;gap:24px;padding:24px", ".deck{display:flex;padding:0"), encoding="utf-8")
                shot(chrome, one, out / f"card-{i + 1}.png", (360, 640))
        ok = shot(chrome, out / "wrapped.html", out / "wrapped.png", (1200, 1400))
        print(f"chat-wrapped: {'card-1..6.png and wrapped.png' if ok else 'PNG failed'} in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
