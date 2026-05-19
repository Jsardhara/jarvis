"""Module entrypoint for ``python -m jarvis.apps.api``.

Runs the FastAPI ASGI app under uvicorn so the documented
launch command works without a wrapper script:

    python -m jarvis.apps.api

Env-overridable:

* ``JARVIS_API_HOST`` — bind host (default ``127.0.0.1``)
* ``JARVIS_API_PORT`` — port (default ``8765``)
* ``JARVIS_API_RELOAD`` — set to ``1`` for dev hot-reload (default off)
* ``JARVIS_API_LOG_LEVEL`` — uvicorn log level (default ``info``)
"""
from __future__ import annotations

import os


def _bool(env_value: str | None) -> bool:
    if not env_value:
        return False
    return env_value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    import uvicorn

    host = os.environ.get("JARVIS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("JARVIS_API_PORT", "8765"))
    reload = _bool(os.environ.get("JARVIS_API_RELOAD"))
    log_level = os.environ.get("JARVIS_API_LOG_LEVEL", "info")

    uvicorn.run(
        "jarvis.apps.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
