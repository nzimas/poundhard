"""PoundHard web UI — download performance recordings.

A tiny self-contained HTTP server (stdlib only) served on move.local:<port>. It is
intentionally structured with routes so more PoundHard functions can be added here
later. Runs in a daemon thread; never blocks the controller.
"""
from __future__ import annotations

import html
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# --- brand -----------------------------------------------------------------
FONT = "https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@400;500;600;700&display=swap"

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 220" class="logo" role="img" aria-label="PoundHard">
  <defs><g id="ph-hash">
    <rect x="30" y="-4" width="17" height="108"/><rect x="59" y="-4" width="17" height="108"/>
    <rect x="-2" y="30" width="108" height="17"/><rect x="-2" y="59" width="108" height="17"/>
  </g></defs>
  <rect x="4" y="4" width="652" height="212" rx="20" fill="#0c0d11"/>
  <rect x="4.5" y="4.5" width="651" height="211" rx="19.5" fill="none" stroke="#26303a"/>
  <g transform="translate(56,52) skewX(-9) scale(1.02)">
    <use href="#ph-hash" transform="translate(-6,3)" fill="#0bd6d0"/>
    <use href="#ph-hash" transform="translate(6,-3)" fill="#ff2e63"/>
    <use href="#ph-hash" fill="#f4f5f7"/>
  </g>
  <text x="212" y="108" font-family="'Chakra Petch',sans-serif" font-weight="700" font-size="66" fill="#f4f5f7">POUND<tspan fill="#ff2e63">HARD</tspan></text>
  <text x="214" y="150" font-family="'Chakra Petch',sans-serif" font-weight="500" letter-spacing="5" font-size="17" fill="#7c8794">16-TRACK MOVE GROOVEBOX</text>
</svg>"""

PAGE = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15">
<title>PoundHard — Recordings</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{font}" rel="stylesheet">
<style>
  :root {{ --bg:#0c0d11; --panel:#14161c; --line:#262b35; --txt:#e9edf2; --dim:#7c8794;
           --hot:#ff2e63; --cy:#0bd6d0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
          font-family:'Chakra Petch',system-ui,sans-serif; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:820px; margin:0 auto; padding:28px 20px 64px; }}
  .logo {{ width:100%; max-width:420px; height:auto; display:block; margin:8px 0 26px; }}
  h1 {{ font-size:15px; letter-spacing:.28em; text-transform:uppercase; color:var(--dim);
        font-weight:600; margin:0 0 18px; }}
  .rec {{ display:flex; align-items:center; gap:16px; background:var(--panel);
          border:1px solid var(--line); border-radius:12px; padding:14px 18px; margin:10px 0; }}
  .rec .n {{ font-size:26px; font-weight:700; color:var(--hot); min-width:44px; }}
  .rec .meta {{ flex:1; }}
  .rec .meta .name {{ font-weight:600; font-size:17px; letter-spacing:.04em; }}
  .rec .meta .sub {{ color:var(--dim); font-size:13px; margin-top:2px; }}
  .rec audio {{ height:34px; }}
  .rec a.dl {{ text-decoration:none; color:var(--bg); background:var(--cy); font-weight:700;
               padding:9px 16px; border-radius:8px; font-size:13px; letter-spacing:.06em; }}
  .rec a.dl:hover {{ background:#3ff0ea; }}
  .empty {{ opacity:.4; }}
  .empty .n {{ color:var(--dim); }}
  footer {{ color:var(--dim); font-size:12px; letter-spacing:.12em; margin-top:30px;
            border-top:1px solid var(--line); padding-top:14px; }}
</style></head>
<body><div class="wrap">
{logo}
<h1>Performance Recordings</h1>
{rows}
<footer>PoundHard · stereo WAV · up to 7 min each · this page auto-refreshes</footer>
</div></body></html>"""


def _wav_info(path: Path):
    """(duration_seconds or None, size_bytes) by reading the WAV header."""
    size = path.stat().st_size
    try:
        with path.open("rb") as f:
            head = f.read(4096)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return None, size
        # find 'fmt ' and 'data' chunks
        i, ch, sr, bits, data = 12, 2, 48000, 24, None
        while i + 8 <= len(head):
            cid = head[i:i + 4]
            csz = struct.unpack("<I", head[i + 4:i + 8])[0]
            if cid == b"fmt ":
                ch = struct.unpack("<H", head[i + 10:i + 12])[0]
                sr = struct.unpack("<I", head[i + 12:i + 16])[0]
                bits = struct.unpack("<H", head[i + 22:i + 24])[0]
            elif cid == b"data":
                data = csz if csz not in (0, 0xFFFFFFFF) else (size - (i + 8))
                break
            i += 8 + csz + (csz & 1)
        if data and ch and sr and bits:
            return data / (sr * ch * (bits // 8)), size
    except (OSError, struct.error):
        pass
    return None, size


def _fmt_dur(sec):
    if sec is None:
        return "—"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def _fmt_size(b):
    return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b / 1024:.0f} KB"


class _Handler(BaseHTTPRequestHandler):
    rec_dir: Path = Path(".")
    n_slots: int = 8

    def log_message(self, *_a):
        pass  # quiet

    def _send(self, code, ctype, body: bytes, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", self._index().encode())
        if path == "/logo.svg":
            return self._send(200, "image/svg+xml", LOGO_SVG.encode())
        if path.startswith("/rec/"):
            name = path[len("/rec/"):]
            if name.startswith("rec_") and name.endswith(".wav") and "/" not in name and ".." not in name:
                f = self.rec_dir / name
                if f.is_file():
                    return self._send(200, "audio/wav", f.read_bytes(),
                                      {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, "text/plain", b"not found")
        return self._send(404, "text/plain", b"not found")

    def _index(self) -> str:
        rows = []
        for slot in range(self.n_slots):
            f = self.rec_dir / f"rec_{slot:02d}.wav"
            if f.is_file() and f.stat().st_size > 44:
                dur, size = _wav_info(f)
                rows.append(
                    f'<div class="rec"><div class="n">{slot + 1}</div>'
                    f'<div class="meta"><div class="name">rec_{slot:02d}.wav</div>'
                    f'<div class="sub">{_fmt_dur(dur)} &nbsp;·&nbsp; {_fmt_size(size)}</div></div>'
                    f'<audio controls preload="none" src="/rec/rec_{slot:02d}.wav"></audio>'
                    f'<a class="dl" href="/rec/rec_{slot:02d}.wav" download>DOWNLOAD</a></div>')
            else:
                rows.append(
                    f'<div class="rec empty"><div class="n">{slot + 1}</div>'
                    f'<div class="meta"><div class="name">— empty —</div></div></div>')
        return PAGE.format(font=html.escape(FONT), logo=LOGO_SVG, rows="\n".join(rows))


def serve(port: int, rec_dir: Path, n_slots: int) -> None:
    """Start the web UI in a daemon thread. Never raises into the caller."""
    _Handler.rec_dir = Path(rec_dir)
    _Handler.n_slots = n_slots
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    except OSError as e:
        print(f"[poundhard] web UI could not bind :{port} ({e})", flush=True)
        return
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    print(f"[poundhard] web UI on http://0.0.0.0:{port}", flush=True)
