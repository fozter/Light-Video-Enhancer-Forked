"""GUI-free command-line entry point used by the standalone backend EXE."""

import ctypes
import json
import os
import sys
import threading
import zipfile
from typing import Iterable, List, Optional

from ._logging import get_logger
from .progress_output import emit_progress, exit_past_stdio


_log = get_logger("backend")


def _remove_flag(argv: Iterable[str], flag: str):
    values = list(argv)
    present = flag in values
    return present, [value for value in values if value != flag]


def _progress_json(stage: str, current: int, total: int) -> None:
    emit_progress(stage, current, total)


def _configure_stdio() -> None:
    """Use UTF-8 for redirected output and both Windows console languages."""
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except (AttributeError, OSError, ValueError):
            pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _listen_for_control(enhancer) -> None:
    """Accept lightweight commands from a parent GUI without extra IPC deps."""
    try:
        for line in sys.stdin:
            if line.strip().lower() == "cancel":
                enhancer.cancel()
                return
    except (OSError, ValueError):
        return


def _wait_for_interactive_close() -> None:
    """Keep an Explorer-launched console open long enough to read an error."""
    isatty = getattr(sys.stdin, "isatty", None)
    if not callable(isatty) or not isatty():
        return
    try:
        input("\nProcessing could not start. Press Enter to close this window.")
    except (EOFError, KeyboardInterrupt, OSError):
        pass


def main(argv: Optional[List[str]] = None) -> None:
    """Run the complete CLI without importing Tkinter or any GUI module."""
    _configure_stdio()
    values = list(sys.argv[1:] if argv is None else argv)

    interactive_session = not values or values == ["--interactive"]
    from .frontend_protocol import handle_frontend_command
    try:
        handled = handle_frontend_command(values, _progress_json)
    except (FileNotFoundError, OSError, RuntimeError, ValueError,
            zipfile.BadZipFile) as exc:
        _log.error("%s", exc)
        # The no-console GUI launch leaves an un-drained stdout/stderr pipe;
        # interpreter shutdown would block forever on the final flush.
        # exit_past_stdio swaps streams past teardown entirely so the GUI
        # sees the command finish via process exit.
        if not interactive_session:
            exit_past_stdio(1)
        raise SystemExit(1)
    if handled:
        # Hard-exit past interpreter/bootloader teardown: the exit wedge
        # parks the worker after the files land even with all app writes
        # non-blocking, so never return into normal shutdown here.
        # (exit_past_stdio performs no os.dup2: the CRT descriptor lock may
        # be held by a writer blocked in os.write to the full pipe.)
        if not interactive_session:
            exit_past_stdio(0)
        return

    if not values or values == ["--interactive"]:
        from .cli_app import interactive_arguments
        values = interactive_arguments()
        if not values:
            return

    if "--system-info" in values:
        from .utils import print_system_info
        print_system_info(deep="--deep" in values)
        return
    if values == ["--version"]:
        from . import __version__
        print(__version__)
        return

    progress_json, values = _remove_flag(values, "--progress-json")
    control_stdin, values = _remove_flag(values, "--control-stdin")

    # Parse first so --help and syntax errors stay fast and dependency-light.
    from .cli import parse_args
    config = parse_args(values)

    from .pipeline import ProcessingCancelled, VideoEnhancer
    exit_code = 0
    try:
        enhancer = VideoEnhancer(
            config, progress_callback=_progress_json if progress_json else None)
        if control_stdin:
            threading.Thread(
                target=_listen_for_control, args=(enhancer,),
                name="lve-control", daemon=True).start()
        enhancer.run()
    except ProcessingCancelled as exc:
        _log.warning("%s", exc)
        exit_code = 130
    except (FileNotFoundError, FileExistsError, ImportError,
            RuntimeError, ValueError) as exc:
        _log.error("%s", exc)
        exit_code = 1
    except KeyboardInterrupt:
        _log.warning("Cancelled by user")
        exit_code = 130
    except Exception as exc:
        _log.exception("Unexpected CLI error: %s", exc)
        exit_code = 1
    finally:
        # No detach here: detach_stdio()'s os.dup2 must take the CRT
        # descriptor lock, which the progress writer may hold while blocked
        # in os.write to a full pipe (native-stack proven deadlock).
        # exit_past_stdio() below exits without any CRT-level surgery.
        pass
    if not interactive_session:
        exit_past_stdio(exit_code)
    if exit_code:
        raise SystemExit(exit_code)
