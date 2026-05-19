from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
import subprocess
import threading
from typing import Literal


LogStream = Literal["stdout", "stderr"]


@dataclass(slots=True)
class ProcessLogEvent:
    timestamp: str
    stream: LogStream
    text: str


class DashboardProcessManager:
    """Single-process manager for the local personal dashboard."""

    def __init__(self, *, max_log_events: int = 4000) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._queue: Queue[ProcessLogEvent] = Queue()
        self._logs: deque[ProcessLogEvent] = deque(maxlen=max_log_events)
        self._lock = threading.Lock()
        self._reader_threads: list[threading.Thread] = []

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def status(self) -> str:
        with self._lock:
            if self._process is None:
                return "idle"
            code = self._process.poll()
            if code is None:
                return "running"
            if code == 0:
                return "completed"
            return "failed"

    def return_code(self) -> int | None:
        with self._lock:
            if self._process is None:
                return None
            return self._process.poll()

    def start(self, command: list[str], *, cwd: Path) -> tuple[bool, str]:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False, "A crawl process is already running."

            self._logs.clear()
            self._drain_queue_locked()

            self._process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            self._reader_threads = []
            if self._process.stdout is not None:
                thread = threading.Thread(
                    target=self._stream_reader,
                    args=(self._process.stdout, "stdout"),
                    daemon=True,
                )
                thread.start()
                self._reader_threads.append(thread)

            if self._process.stderr is not None:
                thread = threading.Thread(
                    target=self._stream_reader,
                    args=(self._process.stderr, "stderr"),
                    daemon=True,
                )
                thread.start()
                self._reader_threads.append(thread)

            return True, "Process started."

    def stop(self, *, timeout_seconds: float = 5.0) -> tuple[bool, str]:
        with self._lock:
            process = self._process

        if process is None or process.poll() is not None:
            return False, "No running process found."

        process.terminate()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout_seconds)

        self.poll_logs()
        return True, "Process stopped."

    def send_input(self, value: str) -> tuple[bool, str]:
        with self._lock:
            process = self._process

        if process is None or process.poll() is not None:
            return False, "Cannot send input because no process is running."

        if process.stdin is None:
            return False, "Process stdin is unavailable."

        process.stdin.write(value + "\n")
        process.stdin.flush()
        return True, "Input sent."

    def add_local_log(self, text: str, *, stream: LogStream = "stdout") -> None:
        if not text.strip():
            return
        with self._lock:
            self._logs.append(
                ProcessLogEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    stream=stream,
                    text=text.strip(),
                ),
            )

    def poll_logs(self) -> None:
        with self._lock:
            self._drain_queue_locked()

    def get_logs(self, *, limit: int = 400) -> list[ProcessLogEvent]:
        self.poll_logs()
        with self._lock:
            if limit <= 0:
                return list(self._logs)
            return list(self._logs)[-limit:]

    def _stream_reader(self, stream_handle, stream_name: LogStream) -> None:
        for line in iter(stream_handle.readline, ""):
            stripped = line.rstrip("\n")
            if not stripped:
                continue
            self._queue.put(
                ProcessLogEvent(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    stream=stream_name,
                    text=stripped,
                ),
            )
        stream_handle.close()

    def _drain_queue_locked(self) -> None:
        while True:
            try:
                self._logs.append(self._queue.get_nowait())
            except Empty:
                break
