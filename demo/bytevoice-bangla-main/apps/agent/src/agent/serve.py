"""Run the LiveKit worker and the HTTP API together, for hosts that run one container per service."""

import logging
import os
import signal
import subprocess
import sys
import threading

import uvicorn

from agent.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def _supervise(worker: subprocess.Popen[bytes]) -> None:
    exit_code = worker.wait()
    logger.error(
        "voice worker exited; stopping the service so the platform restarts it",
        extra={"exit_code": exit_code},
    )
    os.kill(os.getpid(), signal.SIGTERM)


def main() -> None:
    worker = subprocess.Popen([sys.executable, "-m", "agent.worker", "start"])
    threading.Thread(target=_supervise, args=(worker,), daemon=True).start()
    try:
        uvicorn.run(
            "agent.api.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_level="info"
        )
    finally:
        if worker.poll() is None:
            worker.terminate()


if __name__ == "__main__":
    main()
