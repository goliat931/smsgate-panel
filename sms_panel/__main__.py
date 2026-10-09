"""Uruchomienie: python -m sms_panel [--demo] [--port N] [--no-browser]"""
import argparse
import logging
import socket
import sys
import threading
import webbrowser

import httpx
import uvicorn

from .db import DB, data_dir
from .demo import seed
from .web import create_app


def free_port(preferred):
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise SystemExit("Brak wolnego portu.")


def main():
    p = argparse.ArgumentParser(description="SMS Panel")
    p.add_argument("--demo", action="store_true", help="tryb demo: atrapa telefonu, nic nie jest wysyłane")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()
    for stream in (sys.stdout, sys.stderr):  # polskie znaki w starej konsoli Windows
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    folder = data_dir(args.demo)
    port_file = folder / "port"
    # Drugie kliknięcie w ikonę: nie uruchamiaj drugiej kopii (podwójna wysyłka!), tylko pokaż panel.
    try:
        old = int(port_file.read_text())
        if httpx.get(f"http://127.0.0.1:{old}/_ping", timeout=1).text == "SmsPanel":
            print("Panel już działa - otwieram go w przeglądarce.")
            webbrowser.open(f"http://127.0.0.1:{old}")
            return
    except (OSError, ValueError, httpx.HTTPError):
        pass

    port = args.port or free_port(8766 if args.demo else 8765)
    port_file.write_text(str(port))
    url = f"http://127.0.0.1:{port}"
    db = DB(folder / "panel.db")
    if args.demo:
        seed(db)  # przykładowe kontakty, grupy i rozmowy (tylko do pustej bazy)
    app = create_app(db, demo=args.demo, port=port)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    print(f"\n  Panel SMS działa{' (TRYB DEMO)' if args.demo else ''}. Nie zamykaj tego okna.\n"
          f"  Adres panelu: {url}\n  Aby zakończyć, zamknij to okno.\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
