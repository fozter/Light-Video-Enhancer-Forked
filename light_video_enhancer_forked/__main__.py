import json
import sys
import threading
import zipfile

from ._logging import get_logger

_log = get_logger("main")

from .progress_output import emit_progress, exit_past_stdio


def _remove_flag(argv, flag):
    present = flag in argv
    return present, [value for value in argv if value != flag]


def _progress_json(stage: str, current: int, total: int) -> None:
    emit_progress(stage, current, total)


def _configure_stdio() -> None:
    """Keep the JSON-line protocol stable in frozen and legacy consoles."""
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




def main(cli_only: bool = False) -> None:
    _configure_stdio()
    argv = sys.argv[1:]
    from .frontend_protocol import handle_frontend_command
    interactive_run = (not argv) or argv == ["--interactive"] or (not argv and cli_only)
    try:
        handled = handle_frontend_command(argv, _progress_json)
    except (FileNotFoundError, OSError, RuntimeError, ValueError,
            zipfile.BadZipFile) as exc:
        _log.error("%s", exc)
        # The no-console GUI launch leaves an un-drained stdout/stderr pipe;
        # interpreter shutdown would block forever on the final flush.
        # exit_past_stdio swaps streams past teardown entirely so the GUI
        # sees the command finish via process exit.
        if not interactive_run:
            exit_past_stdio(1)
        raise SystemExit(1)
    if handled:
        # Hard-exit past interpreter/bootloader teardown: the exit wedge
        # parks the worker after the files land even with all app writes
        # non-blocking, so never return into normal shutdown here.
        # (exit_past_stdio performs no os.dup2: the CRT descriptor lock may
        # be held by a writer blocked in os.write to the full pipe.)
        if not interactive_run:
            exit_past_stdio(0)
        return

    if not argv and cli_only:
        from .cli_app import interactive_arguments
        argv = interactive_arguments()
        if not argv:
            return
    elif argv == ["--interactive"]:
        from .cli_app import interactive_arguments
        argv = interactive_arguments()
        if not argv:
            return
    elif not argv or argv == ["--gui"] or argv == ["-g"]:
        from .gui import main as gui_main
        gui_main()
        return
    if "--system-info" in argv:
        from .utils import print_system_info
        print_system_info(deep="--deep" in argv)
        return
    if argv == ["--version"]:
        from . import __version__
        print(__version__)
        return
    progress_json, argv = _remove_flag(argv, "--progress-json")
    control_stdin, argv = _remove_flag(argv, "--control-stdin")
    # Parse first so --help and syntax errors stay fast, and their output is
    # never swallowed by the stdio detach below (argparse exits before it).
    from .cli import parse_args
    config = parse_args(argv)
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
    if not interactive_run:
        exit_past_stdio(exit_code)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
