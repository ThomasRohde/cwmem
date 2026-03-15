from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from cwmem.gui.api import build_router

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(root: Path) -> FastAPI:
    app = FastAPI(title="cwmem GUI", docs_url=None, redoc_url=None)
    router = build_router(root)
    app.include_router(router)
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
    return app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server(root: Path, *, port: int = 0, no_open: bool = False) -> None:
    import uvicorn

    if port == 0:
        port = find_free_port()

    url = f"http://127.0.0.1:{port}"
    print(f"cwmem gui starting at {url}", file=sys.stderr)

    if not no_open:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()

    app = create_app(root)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
