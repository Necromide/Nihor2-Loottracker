import argparse
import os
import sys
import threading
import webbrowser

from . import config
from .server import App, serve


def default_data_dir():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="loottracker", description=config.APP_NAME)
    ap.add_argument("--data", default=default_data_dir(), help="folder for the database (default: ./data)")
    ap.add_argument("--client", default=None, help="path to the game client folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    app = App(args.data, args.client)
    app.start()
    httpd, port = serve(app, args.port)
    url = f"http://127.0.0.1:{port}/"
    print(f"{config.APP_NAME} {config.APP_VERSION} läuft auf {url}  (Fenster offen lassen, Strg+C beendet)", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.importer.stop()


if __name__ == "__main__":
    main()
