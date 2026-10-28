# AGENTS.md: chat-wrapped

Reads a WhatsApp chat export (.txt from Export chat > Without media) on this machine. It makes six year-in-review story cards (HTML, optional PNGs) or searches the chat with whatsapp-mcp's rules. Commands run from the repo root; Python 3.8+ standard library only.

## When to use
- "Make a wrapped / year in review of my WhatsApp chat", "who texts more", "what time do we talk most".
- "When did X say ...?", "find the message about the flights" in an exported WhatsApp chat.

## How
```bash
python chat_wrapped.py "WhatsApp Chat with Maya.txt" -o out           # out/wrapped.html, six cards that decode in
python chat_wrapped.py chat.txt -o out --png --title "Maya & Leo"     # also card-1..6.png + wrapped.png (Chrome or Edge)
python chat_wrapped.py chat.txt --search "flight*" booked for thursday --sender leo --since 2026-03-01
python chat_wrapped.py chat.txt --search lease --json                 # one JSON object per hit
```
- Query rules: whole words, case and accents ignored, all words must appear, "quoted phrase" in order, word* for word starts, newest first.
- Wrong dates (day/month swapped)? Add `--dates mdy` or `--dates dmy`. Only one year: `--year 2026`.

## Care
- The chat is private: never upload it, paste it into a web service, or quote more of it than the user asked for.
- If the user has no export yet: WhatsApp > open the chat > tap the name > Export chat > Without media.
