"""Non-blocking progress output for the JSON-line frontend protocol.

The standalone backend is launched by the WinUI app with stdout redirected
and no console window (CreateNoWindow). Under those conditions the frozen
bootloader can leave the child's stdout pipe with no active reader, so a
synchronous print(..., flush=True) blocks forever once the pipe buffer
fills. That is the exact mechanism behind downloads wedging at 208 MiB:
the default 4 KiB pipe buffer holds about 52 progress lines of ~80 bytes,
and each 4 MiB read chunk emits one line. Progress updates are advisory,
so they are serialized through a background daemon writer: when the pipe
is full the writer stalls harmlessly and later updates are dropped instead
of freezing the download itself.

The writer deliberately uses raw os.write() on the descriptor instead of
the stdout TextIOWrapper. A TextIOWrapper serializes access with its own
lock; if the daemon writer blocked inside print() while holding that lock,
the main thread's stdout writes (for example the final result line of a
model command) would deadlock on the same lock even though the pipe is
only 'advisory'-full. Raw descriptor writes have no coarser lock to
contend over, and a daemon thread stuck in a system write never blocks
interpreter shutdown (daemon threads are not joined).
"""

import json
import os
import queue
import sys
import threading

_PROGRESS_PREFIX = "__LVE_PROGRESS__"
_QUEUE_CAPACITY = 256

__all__ = ["emit_progress", "emit_line", "exit_past_stdio"]

_LOCK = threading.Lock()
_WRITER = None


class _ProgressWriter:
    """Serializes progress and advisory stdout lines on a daemon thread."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=_QUEUE_CAPACITY)
        self._thread = threading.Thread(
            target=self._run,
            name="lve-progress-writer",
            daemon=True,
        )
        self._thread.start()

    def emit(self, stage: str, current: int, total: int) -> None:
        payload = {"stage": stage, "current": int(current), "total": int(total)}
        line = _PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=True)
        self._enqueue(line)

    def line(self, message: str) -> None:
        self._enqueue(message)

    def _enqueue(self, line: str) -> None:
        try:
            self._queue.put_nowait(line.encode("utf-8", "replace") + b"\n")
        except queue.Full:
            # Drop advisory output rather than stall the transfer or let the
            # final result line block the command's completion.
            pass

    def _run(self) -> None:
        while True:
            data = self._queue.get()
            try:
                # Raw descriptor write: no TextIOWrapper buffering or lock, so
                # a blocked write can never stall other stdout writers.
                os.write(1, data)
            except (OSError, ValueError):
                pass


def _writer() -> _ProgressWriter:
    global _WRITER
    if _WRITER is None:
        with _LOCK:
            if _WRITER is None:
                _WRITER = _ProgressWriter()
    return _WRITER


def emit_progress(stage: str, current: int, total: int) -> None:
    """Best-effort progress reporting that can never block its caller."""
    _writer().emit(stage, current, total)


def emit_line(message: str) -> None:
    """Best-effort raw stdout line (no protocol prefix) that never blocks.

    Used for the result line of long-running model commands. The delivery
    guarantee mirrors progress: it is dropped if the writer is saturated
    behind an un-drained pipe. Frontend completion is signalled by the
    process exiting, not by this line, so dropping it is safe.
    """
    _writer().line(message)


def exit_past_stdio(code: int) -> None:
    """Swap Python-level streams to memory, then terminate past teardown.

    Even with every app-level write non-blocking, CPython/PyInstaller
    shutdown (module finalizers, logging shutdown flush, bootloader child
    reaping) can still park forever against un-drained GUI pipes -- and so
    could any CRT-level descriptor surgery: ``os.dup2`` must take the CRT
    descriptor lock, which a daemon writer thread may already hold while
    blocked inside ``os.write`` to a full pipe (observed native stack:
    main in ``ucrtbase!_dup2_internal`` / ``RtlEnterCriticalSection``
    while the writer sits in ``WriteFile``). The real outputs are already
    on disk (closed + atomically replaced) before any exit point, and
    frontend completion is signalled by process exit, so this path
    performs no CRT-level descriptor surgery at all: standard streams are
    repointed to a memory buffer (pure Python, no CRT locks, nothing that
    can block on a pipe), logging handlers captured at import time are
    repointed with it, and ``os._exit`` ends the process without running
    finalizers, atexit handlers, or stdio flushes. Never returns.
    Interactive sessions must keep the normal return/SystemExit path and
    never call this.
    """
    try:
        import io as _io

        sink = _io.StringIO()
        try:
            sys.stdout = sink
        except Exception:
            pass
        try:
            sys.stderr = sink
        except Exception:
            pass
        try:
            import logging as _logging

            for _logger_name in (None, "lve"):
                try:
                    _logger = _logging.getLogger(_logger_name)
                except Exception:
                    continue
                for _handler in list(getattr(_logger, "handlers", None) or ()):
                    try:
                        if getattr(_handler, "stream", None) is not sink:
                            _handler.stream = sink
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass
    os._exit(int(code))
