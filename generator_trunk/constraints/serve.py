#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

r"""serve — the zero-dependency local host for the constraint editor (the auto-invoke seam).

The running pipeline calls `serve_editor(sheets, sidecar)`; this serves the single-file editor over
the stdlib http.server (no Flask, no node), opens it in Firefox, and BLOCKS until the user presses
Submit — at which point the page POSTs its sidecar back to `/submit` and the chain resumes. Drawing
nothing and pressing Submit is a valid outcome: it returns an empty-constraints sidecar, which the
sieve stage treats as a no-op ("as if --sieve was off").

  python3 serve.py --spec <spec>      # stand-alone: serve a real spec's sheets, print the result
"""
from __future__ import annotations

import http.server
import json
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor as ed  # noqa: E402


def _open_browser(url: str, browser: str | None) -> None:
    for getter in ([browser] if browser else []) + [None]:
        try:
            (webbrowser.get(getter) if getter else webbrowser).open(url)
            return
        except Exception:
            continue
    print(f"  open this URL in your browser: {url}", flush=True)


def serve_editor(sheets: dict, sidecar: dict | None = None, *, title: str | None = None,
                 host: str = "127.0.0.1", port: int = 0, lang: str = "ru",
                 open_browser: bool = True, browser: str | None = "firefox",
                 timeout: float | None = None, impact_fn=None, optional_sheets=None) -> dict | None:
    """Serve the editor, open it, and wait for Submit. Returns the POSTed sidecar dict, or None if
    the editor was closed/timed out without submitting. `port=0` picks a free port.

    `impact_fn(sidecar) -> dict` (optional) enables EXACT live impact: the page POSTs the current
    sidecar to `/impact` on every change and shows the precise removed/kept this returns. Absent =>
    the page uses its offline in-browser estimate (the default)."""
    impact_url = "/impact" if impact_fn else ""
    html = ed.render_html(sheets, sidecar, post="/submit", title=title, lang=lang,
                          impact=impact_url, optional_sheets=optional_sheets).encode("utf-8")
    result: dict = {"sidecar": None, "submitted": False}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, html)
            elif self.path == "/favicon.ico":
                self._send(204, b"")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self):  # noqa: N802
            if self.path == "/submit":
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    result["sidecar"] = json.loads(raw or b"{}")
                    result["submitted"] = True
                except Exception:
                    result["sidecar"] = None
                self._send(200, b'{"ok":true}', "application/json")
                done.set()
            elif self.path == "/impact" and impact_fn is not None:
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    out = impact_fn(json.loads(raw or b"{}"))
                except Exception as exc:                       # never break the editor on an impact error
                    out = {"exact": False, "error": str(exc)}
                self._send(200, json.dumps(out).encode("utf-8"), "application/json")
            else:
                self._send(404, b"")

        def log_message(self, *_a):  # silence the default request logging
            pass

    httpd = http.server.ThreadingHTTPServer((host, port), Handler)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"  link editor live at {url}  (draw your forbidden/required bonds, then press Submit)", flush=True)
    if open_browser:
        _open_browser(url, browser)
    try:
        done.wait(timeout)
    except KeyboardInterrupt:
        print("  (interrupted — proceeding without added constraints)", flush=True)
    finally:
        httpd.shutdown()
        httpd.server_close()
    return result["sidecar"] if result["submitted"] else None


def _argval(flag, default=None):
    a = sys.argv[1:]
    return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default


def main():
    from graphspec import spec_sheets
    spec = _argval("--spec")
    if not spec:
        print(__doc__)
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import fwgen as fg
    loaded = fg.load_spec(spec)
    sheets = spec_sheets(spec)
    sidecar = {"version": 1, "params": loaded.params, "constraints": loaded.constraints}
    optional_sheets = {s.sheet for s in loaded.slots if "FW_Optional" in s.flags}
    result = serve_editor(sheets, sidecar, title=f"Bundle — {Path(spec).stem}", optional_sheets=optional_sheets)
    print("\nresult:", json.dumps(result, ensure_ascii=False, indent=2) if result else "(closed without Submit)")


if __name__ == "__main__":
    main()
