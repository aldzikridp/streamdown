#!/usr/bin/env python3
"""Regression check: the pty handed to --exec must report the real terminal size.

A fresh pty has a 0x0 window size. Line editors (readline/click/prompt_toolkit)
then fall back to 80 columns and desync their cursor maths once the input line
passes that width, so typing at the end of the line looks jumbled.

The child writes the size *it* sees to a file, then blocks on stdin.
Stdlib only; streamdown's own runtime deps must be importable.

    python3 tests/test-exec-winsize.py [path/to/sd.py]
"""
import fcntl
import os
import pty
import struct
import subprocess
import sys
import tempfile
import termios
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "streamdown", "sd.py")
COLS, ROWS = 123, 41

CHILD_SOURCE = """\
import os, sys
size = os.get_terminal_size(1)
open(os.environ["SD_SIZE_OUT"], "w").write(f"{size.columns} {size.lines}")
sys.stdin.read()
"""


def write_child():
    fd, path = tempfile.mkstemp(suffix=".py", prefix="sd-winsize-child-")
    with os.fdopen(fd, "w") as fh:
        fh.write(CHILD_SOURCE)
    return path


def read_size(path, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(path) as fh:
                data = fh.read().strip()
            if data:
                return data
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    return ""


def main():
    child = write_child()
    size_out = child + ".size"
    stdin_pty = pty.openpty()
    stdout_pty = pty.openpty()
    try:
        # the terminal sd itself is attached to
        fcntl.ioctl(stdin_pty[1], termios.TIOCSWINSZ,
                    struct.pack("HHHH", ROWS, COLS, 0, 0))
        env = dict(os.environ, SD_SIZE_OUT=size_out)
        proc = subprocess.Popen(
            [sys.executable, SD, "--exec", f"{sys.executable} {child}"],
            stdin=stdin_pty[1], stdout=stdout_pty[1], stderr=stdout_pty[1],
            env=env,
        )
        os.close(stdin_pty[1])
        os.close(stdout_pty[1])
        seen = read_size(size_out)
        proc.kill()
        proc.wait()
    finally:
        os.close(stdout_pty[0])
        os.close(stdin_pty[0])
        os.unlink(child)
        if os.path.exists(size_out):
            os.unlink(size_out)

    assert seen == f"{COLS} {ROWS}", (
        f"child saw terminal size {seen!r}, expected {COLS} {ROWS}"
    )
    print(f"ok: --exec child sees the real terminal size ({COLS}x{ROWS})")


if __name__ == "__main__":
    main()
