"""Web window into the mind (§11.7, row 50).

Traceability: ARCHITECTURE §11.7 (a browser interface served from inside the
process — one window that shows everything: dialogue, reminders, permission
asks, episodes; voice in both directions through the browser's own speech
recognition and synthesis — ears and mouth with zero installs) and §8
(standard-library-only serving of the window plus a tiny JSON API; the mind
is untouched: the UI talks to Mind.step/Memory exactly like the CLI does).

Run it:

    python -m beanie.webui --state-dir .beanie_state --port 8080

then open http://localhost:8080 in a browser. Bind 0.0.0.0 to reach it from
other devices on the same LAN (the phone, the Android app concept).
"""

from __future__ import annotations

import datetime
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .mind import Mind

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Beanie</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --line:#2d333b; --txt:#c9d1d9;
          --dim:#8b949e; --accent:#4f8fe8; --you:#1f6feb; --beanie:#238636; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 system-ui,sans-serif; background:var(--bg); color:var(--txt);
         display:flex; flex-direction:column; height:100vh; }
  header { display:flex; align-items:center; gap:.6rem; padding:.7rem 1rem;
           border-bottom:1px solid var(--line); background:var(--panel); }
  header .logo { font-weight:700; letter-spacing:.4px; }
  header .badge { font-size:.72rem; color:var(--dim); border:1px solid var(--line);
                  border-radius:1rem; padding:.1rem .55rem; }
  #state { margin-left:auto; display:flex; gap:.4rem; font-size:.72rem; flex-wrap:wrap; }
  .chip { border:1px solid var(--line); border-radius:1rem; padding:.1rem .55rem; color:var(--dim); }
  .chip.warn { color:#e3b341; border-color:#6e5c18; }
  main { flex:1; overflow-y:auto; padding:1rem; display:flex; flex-direction:column; gap:.7rem; }
  .msg { max-width:76ch; padding:.65rem .9rem; border-radius:.8rem; white-space:pre-wrap; }
  .msg.you { align-self:flex-end; background:var(--you); color:#fff; border-bottom-right-radius:.2rem; }
  .msg.beanie { align-self:flex-start; background:var(--panel); border:1px solid var(--line);
                border-bottom-left-radius:.2rem; }
  .msg .label { display:block; font-size:.68rem; color:var(--dim); margin-top:.35rem; }
  .msg.notice { align-self:center; background:none; border:1px dashed var(--line); color:var(--dim);
                font-size:.8rem; }
  form { display:flex; gap:.5rem; padding:.8rem 1rem; border-top:1px solid var(--line);
         background:var(--panel); }
  input#text { flex:1; background:var(--bg); color:var(--txt); border:1px solid var(--line);
               border-radius:.5rem; padding:.65rem .8rem; font:inherit; }
  button { border:1px solid var(--line); background:var(--panel); color:var(--txt);
           border-radius:.5rem; padding:.6rem .9rem; cursor:pointer; font:inherit; }
  button:hover { border-color:var(--accent); }
  button.mic.live { background:#8e2b2b; border-color:#b40000; color:#fff; }
</style>
</head>
<body>
<header>
  <span class="logo">◉ Beanie</span>
  <span class="badge" id="backend">connecting…</span>
  <div id="state"></div>
</header>
<main id="log"></main>
<form id="f">
  <button type="button" class="mic" id="mic" title="talk (browser speech recognition)">🎤</button>
  <input id="text" placeholder="Say or type anything… try “play me kaba”" autocomplete="off"/>
  <button type="submit">Send</button>
  <button type="button" id="tick" title="let Beanie think on its own">Tick</button>
</form>
<script>
const log = document.getElementById('log');
const speaking = localStorage.getItem('beanie.voice') !== 'off';

function add(cls, text, label) {
  const el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.textContent = text;
  if (label) { const l = document.createElement('span'); l.className = 'label'; l.textContent = label; el.appendChild(l); }
  log.appendChild(el); log.parentElement.scrollTop = log.parentElement.scrollHeight;
}
async function post(url, body) {
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                              body: JSON.stringify(body)});
  return r.json();
}
function speak(text) {
  if (!speaking || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/^[a-z][a-z·-]* → /, ''));
  u.rate = 1.0; speechSynthesis.speak(u);
}
async function send(text) {
  add('you', text);
  const r = await post('/api/step', {text});
  add('beanie', r.text, r.confidence_label);
  (r.reminders || []).forEach(x => add('notice', '⏰ ' + x));
  (r.questions || []).forEach(x => add('notice', '❓ ' + x));
  speak(r.text);
  refreshState();
}
document.getElementById('f').addEventListener('submit', e => {
  e.preventDefault();
  const input = document.getElementById('text');
  const text = input.value.trim(); if (!text) return;
  input.value = ''; send(text);
});
document.getElementById('tick').onclick = async () => {
  const r = await post('/api/tick', {});
  (r.notes || []).forEach(n => add('beanie', n.text, n.confidence_label));
  refreshState();
};
document.getElementById('mic').onclick = () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { add('notice', 'This browser has no speech recognition (try Chrome or Edge).'); return; }
  const rec = new SR(); rec.lang = 'en-US'; rec.interimResults = false;
  const mic = document.getElementById('mic'); mic.classList.add('live');
  rec.onresult = e => send(e.results[0][0].transcript);
  rec.onend = () => mic.classList.remove('live');
  rec.onerror = e => { add('notice', 'Mic error: ' + e.error); mic.classList.remove('live'); };
  rec.start();
};
async function refreshState() {
  const s = await (await fetch('/api/state')).json();
  document.getElementById('backend').textContent = s.backend;
  const box = document.getElementById('state'); box.innerHTML = '';
  const chips = [];
  if (s.today && s.today.events) chips.push('today: ' + s.today.events + ' trace events');
  if (s.open_questions) chips.push(s.open_questions + ' open question' + (s.open_questions == 1 ? '' : 's'));
  if (s.active_skills) chips.push(s.active_skills + ' active skill' + (s.active_skills == 1 ? '' : 's'));
  chips.push(s.episodes + ' episodes');
  chips.forEach(c => { const e = document.createElement('span');
    e.className = 'chip warn'; e.textContent = c; box.appendChild(e); });
  (s.queue || []).forEach(item => {
    if (item.kind === 'permission_ask') return;        // asks already render as buttons below
    const e = document.createElement('span');
    e.className = 'chip warn'; e.textContent = '⏸ ' + item.text; box.appendChild(e);
  });
  (s.pending || []).forEach(pend => {
    const wrap = document.createElement('span'); wrap.className = 'chip warn';
    const name = document.createElement('span'); name.textContent = '⚠ ' + pend.capability + ' ×' + pend.count + ' ';
    const allow = document.createElement('button'); allow.textContent = 'allow';
    allow.style.cssText = 'margin:0 .2rem;padding:0 .45rem;font-size:.68rem;';
    allow.onclick = () => send('you may ' + pend.capability);
    const never = document.createElement('button'); never.textContent = 'never';
    never.style.cssText = 'margin:0 .2rem;padding:0 .45rem;font-size:.68rem;color:#e3564e;';
    never.onclick = () => send('never use ' + pend.capability);
    wrap.appendChild(name); wrap.appendChild(allow); wrap.appendChild(never);
    box.appendChild(wrap);
  });
}
add('notice', 'Beanie is here — highest-confidence answers are labelled; say "why did you say that?" for its own validation trail.');
refreshState();
</script>
</body>
</html>
"""


class MindHTTPServer(ThreadingHTTPServer):
    """HTTP server holding the mind instance it serves."""

    def __init__(self, address: tuple[str, int], mind: Mind) -> None:
        super().__init__(address, _make_handler())
        self.mind = mind

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server_address[:2]
        return str(host), int(port)


def make_server(mind: Mind, host: str = "127.0.0.1", port: int = 8080) -> MindHTTPServer:
    """Bind a server (port 0 = ephemeral, for tests)."""
    return MindHTTPServer((host, port), mind)


def _make_handler() -> type[BaseHTTPRequestHandler]:

    class Handler(BaseHTTPRequestHandler):
        server: MindHTTPServer

        def _json(self, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

        def _write(self, data: bytes) -> None:
            self.wfile.write(data)

        def log_message(self, *_args: Any) -> None:  # quiet by default
            return None

        # -- routes ----------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802 — stdlib hook name
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                body = _PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._write(body)
                return
            if path == "/api/state":
                memory = self.server.mind.memory
                open_q = len(memory.query(kind="self", type="question", status="open"))
                pending = self.server.mind.pending_permission_requests()
                today = self.server.mind.day_activity(datetime.date.today())
                queue = self.server.mind.work_queue()
                self._json()
                self._write(json.dumps({
                    "backend": self.server.mind.substrate.name,
                    "open_questions": open_q,
                    "pending_permissions": len(pending),
                    "pending": pending,
                    "today": today,
                    "queue": queue,
                    "active_skills": memory.skills.count(),
                    "episodes": memory.episodes.count(),
                }).encode())
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 — stdlib hook name
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                body = {}
            if path == "/api/step":
                text = str(body.get("text", "")).strip()
                try:
                    reply = self.server.mind.step(text)
                except Exception as exc:
                    # a JSON 500 carrying the real failure — the window must
                    # never die because a single turn did (§11.7 honesty)
                    self._json(code=500)
                    self._write(json.dumps({
                        "text": (f"this turn hit an internal error ({type(exc).__name__}: {exc}) — "
                                 f"the request failed, the window did not crash; the server log has the stack"),
                        "confidence_label": "frank insecurity",
                        "turn_id": "", "reminders": [], "questions": [], "error": True,
                    }).encode())
                    return
                self._json()
                self._write(json.dumps({
                    "text": reply.text,
                    "confidence_label": reply.confidence_label,
                    "turn_id": reply.turn_id,
                    "reminders": list(reply.reminders),
                    "questions": list(reply.questions),
                }).encode())
                return
            if path == "/api/tick":
                notes = self.server.mind.tick()  # a real maintenance report (§4.2)
                flat: list[dict[str, str]] = []
                for channel, value in notes.items():
                    if isinstance(value, list):
                        flat.extend({"text": f"[{channel}] {item}", "confidence_label": ""}
                                    for item in value)
                    elif value:
                        flat.append({"text": f"[{channel}] {value}", "confidence_label": ""})
                self._json()
                self._write(json.dumps({"notes": flat}).encode())
                return
            if path == "/api/explain":
                self._json()
                self._write(json.dumps({"explanation": self.server.mind.explain()}).encode())
                return
            self.send_error(404)

    return Handler


def main(argv: Optional[list[str]] = None) -> None:
    import argparse

    from .cli import build_mind

    parser = argparse.ArgumentParser(prog="beanie-webui", description="Beanie's web window (§11.7)")
    parser.add_argument("--state-dir", default=".beanie_state")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 makes it reachable from other devices")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    mind = build_mind(Path(args.state_dir))
    try:
        server = make_server(mind, host=args.host, port=args.port)
    except OSError as exc:
        # the most common first-run trap: a stale window still holds 8080 —
        # say exactly that and exit loud, never trace-dump at the owner
        print(f"◌ cannot open the window on {args.host}:{args.port} — {exc}. "
              f"A previous window is probably still holding the port; close it, "
              f"or restart the window on a different port with --port <number>.",
              flush=True)
        raise SystemExit(3) from exc
    host, port = server.address
    print(f"◉ Beanie's web window is open: http://{host}:{port}/  (Ctrl+C to close)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nwindow closed.")


if __name__ == "__main__":
    main()
