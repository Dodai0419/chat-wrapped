"""Write the made-up example exports (fixed seeds, so the files never change):

    examples/maya-and-leo.txt   two friends, iPhone export format, day/month/year, 24-hour clock
    examples/hiking-club.txt    a group of five, Android export format, month/day/year, 12-hour clock
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

LINES = ["are we still on for thursday?", "running 10 min late sorry", "did you see the sunset tonight 🌅", "coffee tomorrow? ☕",
         "the flights are booked for thursday ✈️", "haha no way 😂", "send me the recipe pls", "on my way", "miss you guys ❤️",
         "who's bringing snacks", "the trail was closed so we took the long loop", "best pizza in town, trust me 🍕",
         "lease signed, deposit paid!!", "can't wait for the weekend 🎉", "happy birthday!!! 🎂🎉", "rain again... 🌧️",
         "found a café that does oat flat whites", "movie night? 🍿", "good morning ☀️", "night night 😴", "that playlist is so good 🎶",
         "sent you the photos from saturday", "train delayed again", "what time is the hike", "bring the big tent ⛺"]
HOME = Path(__file__).parent


def chat(seed, people, n, start, days, fmt, path):
    r = random.Random(seed)
    t, rows = start, []
    active = sorted(r.sample(range(days), int(days * 0.62)))
    for d in active:
        t = start + timedelta(days=d, hours=r.choice([8, 12, 13, 18, 19, 20, 21, 21, 22, 22, 23]), minutes=r.randint(0, 59))
        for _ in range(max(1, int(r.expovariate(1 / (n / len(active)))))):
            who = r.choices(people, weights=range(len(people) + 1, 1, -1))[0]
            body = "<Media omitted>" if fmt == "android" and r.random() < 0.07 else "‎image omitted" if r.random() < 0.07 else r.choice(LINES)
            rows.append((t, who, body))
            t += timedelta(minutes=r.randint(0, 9), seconds=r.randint(0, 59))
    with open(HOME / path, "w", encoding="utf-8", newline="\n") as f:
        f.write(("[01/01/2026, 00:00:00] " if fmt == "ios" else "1/1/26, 12:00 AM - ") + "Messages and calls are end-to-end encrypted.\n")
        for t, who, body in rows:
            if fmt == "ios":
                f.write(f"[{t:%d/%m/%Y, %H:%M:%S}] {who}: {body}\n")
            else:
                f.write(f"{t.month}/{t.day}/{t:%y}, {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} - {who}: {body}\n")
        if fmt == "ios":
            f.write("[31/12/2026, 23:59:00] Maya: happy new year!! 🎆\nsee you in 2027\n")  # a message over two lines


chat(3, ["Maya", "Leo"], 4200, datetime(2026, 1, 1), 364, "ios", "maya-and-leo.txt")
chat(5, ["Ana", "Ben", "Chloe", "Dev", "Eli"], 2600, datetime(2026, 1, 1), 364, "android", "hiking-club.txt")
