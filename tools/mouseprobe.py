#!/usr/bin/env python3
"""Show how a terminal reports the mouse, the way Textual sees it.

Textual enables SGR-pixel mouse reporting (mode 1016) whenever the terminal
supports in-band resize (mode 2048), then converts pixel coordinates to cells
with the pixel size from the 2048 report. If those two disagree about units or
geometry, every Textual app's hover lands on the wrong row. This script draws a
row ruler and prints, for each mouse report, the raw coordinates and the row
Textual would compute, so the mismatch can be read off directly.

    python3 tools/mouseprobe.py            # pixel mode, as Textual uses it
    python3 tools/mouseprobe.py --cells    # plain SGR cell mode, for comparison

Move the mouse over the ruler; the status line at the bottom updates. q quits.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import sys
import termios
import tty

REPORT = re.compile(r"\x1b\[(\?2048;\d\$y|48;\d+;\d+;\d+;\d+t|[4568];\d+;\d+t|<\d+;\d+;\d+[mM])")


def main() -> int:
    cells_only = "--cells" in sys.argv
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    write = lambda s: (sys.stdout.write(s), sys.stdout.flush())
    size = shutil.get_terminal_size()
    tty.setraw(fd)
    rows = cols = ph = pw = None
    log: list[str] = []
    try:
        write("\x1b[2J\x1b[H")
        for r in range(1, size.lines - 1):
            write(f"\x1b[{r};1Hrow {r - 1:3d} " + ("·" * (size.columns - 10)))
        write(f"\x1b[{size.lines};1H\x1b[7m mode: {'SGR cells (1006)' if cells_only else 'SGR pixels (1016), as Textual uses'} — move the mouse, q quits \x1b[0m")
        write("\x1b[?2048$p\x1b[?2048h\x1b[14t\x1b[16t\x1b[18t")
        write("\x1b[?1000h\x1b[?1003h\x1b[?1006h" + ("" if cells_only else "\x1b[?1016h"))
        buf = ""
        while True:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                continue
            data = os.read(fd, 4096).decode("utf-8", "replace")
            if "q" in data and "\x1b" not in data:
                break
            buf += data
            for m in REPORT.finditer(buf):
                s = m.group(1)
                if s.startswith("48;"):
                    rows, cols, ph, pw = map(int, s[3:-1].split(";"))
                    log.append(f"in-band size: rows={rows} cols={cols} px_h={ph} px_w={pw} -> cell {pw / cols:.2f} x {ph / rows:.2f} px")
                elif s.startswith("?2048"):
                    log.append(f"mode 2048 reply: CSI {s} (2 = supported, off; 1 = on; 0 = unsupported)")
                elif s[0] in "4568":
                    log.append(f"window report: CSI {s}")
                elif s.startswith("<"):
                    _, x, y = map(int, s[1:-1].split(";"))
                    if cells_only:
                        status = f"cell report x={x:4d} y={y:4d} -> row {y - 1}"
                    elif rows and ph:
                        status = f"pixel report x={x:5d} y={y:5d} -> Textual row {(y - 1) / (ph / rows):6.2f} col {(x - 1) / (pw / cols):6.2f}"
                    else:
                        status = f"pixel report x={x:5d} y={y:5d} (no in-band size yet)"
                    write(f"\x1b[{size.lines - 1};1H\x1b[2K{status}")
            buf = buf[-300:]
            for i, line in enumerate(log[-4:]):
                write(f"\x1b[{size.lines - 6 + i};1H\x1b[2K\x1b[1m{line}\x1b[0m")
    finally:
        write("\x1b[?1016l\x1b[?1006l\x1b[?1003l\x1b[?1000l\x1b[?2048l")
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        write(f"\x1b[{size.lines};1H\r\n")
        for line in log:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
