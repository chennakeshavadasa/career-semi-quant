"""Dev tool (not shipped): serve the web edition's UI from this checkout with the live website's data, for the
phone audit (uitest.js) where the data sources (Yahoo, the members list...) can't be reached.

    python devtools/liveproxy.py /tmp/site 8060        # builds the UI into /tmp/site, then serves it
    node devtools/uitest.js http://127.0.0.1:8060/ /tmp/ui a360,p412,zoom130,se375light,land800,tab768,desk1400,desk1400light congress,nvda_smart

A data file the folder lacks is fetched once from the website and kept (delete <folder>/data to refresh it);
edit a file there to try a case the live data doesn't have.
"""
import http.server
import os
import sys
import urllib.request
from pathlib import Path

LIVE = "https://nithinpuru.github.io/quant-terminal/app"


def main() -> None:
    root, port = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8060
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from semiquant.publish import Publisher
    Publisher(root).copy_app()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def do_GET(self):
            path = self.path.split("?")[0]
            local = os.path.join(root, path.lstrip("/"))
            if path.startswith("/data/") and not os.path.exists(local):
                try:
                    body = urllib.request.urlopen(LIVE + path, timeout=30).read()
                    os.makedirs(os.path.dirname(local), exist_ok=True)
                    with open(local, "wb") as f:
                        f.write(body)
                except Exception:  # noqa: BLE001 - not on the website either: a 404, as the app expects
                    pass
            return super().do_GET()

        def log_message(self, *a):
            pass
    print(f"serving {root} on http://127.0.0.1:{port}/ (data from {LIVE})")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
