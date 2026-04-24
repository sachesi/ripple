from __future__ import annotations

import shutil
import sys
import time

if sys.stdout.isatty():

    def _c(code: str) -> str:
        return f"\033[{code}m"

    R, BOLD, DIM = _c("0"), _c("1"), _c("2")
    BLUE, CYAN, GREEN, YELLOW, RED = _c("34"), _c("36"), _c("32"), _c("33"), _c("31")
    C_TL = _c("36")
    C_OK = f"{C_TL}│{R}  {_c('1;32')}✔{R}"
    C_INFO = f"{C_TL}│{R}  {_c('1;34')}ℹ{R}"
    C_WARN = f"{C_TL}│{R}  {_c('1;33')}⚠{R}"
    C_ERR = f"{C_TL}│{R}  {_c('1;31')}✖{R}"
    C_STEP = f"{C_TL}●{R}"
else:
    R = BOLD = DIM = ""
    BLUE = CYAN = GREEN = YELLOW = RED = C_TL = ""
    C_OK, C_INFO, C_WARN, C_ERR, C_STEP = "[OK]", "[INFO]", "[WARN]", "[ERR]", "[STEP]"


class UIManager:
    def __init__(self):
        self.tty = sys.stdout.isatty()
        self.inner_text: str | None = None
        self.overall_text: str | None = None
        self.lines_drawn = 0

    def _clear_bars(self):
        if not self.tty:
            return
        sys.stdout.write("\r\033[2K")
        for _ in range(self.lines_drawn):
            sys.stdout.write("\033[1A\r\033[2K")
        self.lines_drawn = 0

    def _draw_bars(self):
        if not self.inner_text and not self.overall_text:
            return
        out = ""
        lines = 0
        if self.inner_text and self.overall_text:
            out = f"{C_TL}│{R}  {self.overall_text}\n{C_TL}│{R}  {self.inner_text}"
            lines = 1
        elif self.inner_text:
            out = f"{C_TL}│{R}  {self.inner_text}"
        elif self.overall_text:
            out = f"{C_TL}│{R}  {self.overall_text}"

        sys.stdout.write(out + "\r")
        sys.stdout.flush()
        self.lines_drawn = lines

    def print(self, msg="", file=sys.stdout):
        if not self.tty:
            print(msg, file=file, flush=True)
            return
        self._clear_bars()
        if file == sys.stdout:
            sys.stdout.write(str(msg) + "\n")
        else:
            sys.stdout.flush()
            print(msg, file=file, flush=True)
        self._draw_bars()

    def set_inner(self, text: str):
        if not self.tty:
            return
        self._clear_bars()
        self.inner_text = text
        self._draw_bars()

    def close_inner(self, static_msg: str):
        if not self.tty:
            return
        self._clear_bars()
        self.inner_text = None
        sys.stdout.write(f"{C_TL}│{R}  {static_msg}\n")
        self._draw_bars()


ui = UIManager()


def info(msg: str) -> None:
    ui.print(f"{C_INFO} {msg}")


def ok(msg: str) -> None:
    ui.print(f"{C_OK} {msg}")


_first_step = True


def step(msg: str, sub: str = "") -> None:
    global _first_step
    prefix = (
        f"{C_TL}│{R}\n{C_TL}├─{R} {C_STEP} {BOLD}{msg}{R}"
        if not _first_step
        else f"{C_TL}╭─{R} {C_STEP} {BOLD}{msg}{R}"
    )
    _first_step = False
    if sub:
        prefix += f" {DIM}({sub}){R}"
    ui.print(prefix)


def warn(msg: str) -> None:
    ui.print(f"{C_WARN} {msg}", file=sys.stderr)


def err(msg: str) -> None:
    ui.print(f"{C_ERR} {msg}", file=sys.stderr)


def done_msg(msg: str) -> None:
    ui.print(f"{C_TL}│{R}\n{C_TL}╰─{R} {GREEN}✔{R} {BOLD}{msg}{R}\n")


class DownloadProgressBar:
    BLOCKS = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

    def __init__(self, title: str) -> None:
        self._title = title
        self._tty = sys.stdout.isatty()
        self._start_time = time.perf_counter()
        if self._tty:
            self.update(0, 0, 1)

    def _format_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def update(self, downloaded: int, total: int, chunk_count: int = 0) -> None:
        if not self._tty:
            if chunk_count % 50 == 0 and total > 0:
                pct = downloaded * 100 // total
                ui.print(f"   Downloading {self._title}... {pct}%")
            return

        pct = downloaded / total if total > 0 else 0
        pct_str = f"{int(pct * 100):3d}%"

        elapsed = time.perf_counter() - self._start_time
        if downloaded > 0 and total > downloaded:
            eta = (elapsed / downloaded) * (total - downloaded)
            time_str = f"[{self._format_time(elapsed)} < {self._format_time(eta)}]"
        else:
            time_str = f"[{self._format_time(elapsed)}]"

        mib_done = downloaded / 1_048_576
        mib_total = total / 1_048_576
        size_str = f"{mib_done:.1f}/{mib_total:.1f} MiB"

        term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
        title_pad = f"{self._title:<15}"
        fixed_len = 2 + len(title_pad) + 2 + 2 + len(size_str) + 3 + len(pct_str) + 2 + len(time_str) + 1
        max_bar_width = 30
        available_width = term_cols - fixed_len - 2
        bar_width = min(max_bar_width, max(10, available_width // 2))

        fill_val = pct * bar_width
        full_blocks = int(fill_val)
        remainder = fill_val - full_blocks

        if downloaded >= total and total > 0:
            bar_chars = "█" * bar_width
            bar_color = GREEN if self._tty else ""
            empty_chars = ""
        else:
            bar_chars = "█" * full_blocks
            if full_blocks < bar_width:
                bar_chars += self.BLOCKS[int(remainder * len(self.BLOCKS))]
                empty_chars = "░" * (bar_width - full_blocks - 1)
            else:
                empty_chars = ""
            bar_color = CYAN if self._tty else ""

        if empty_chars:
            bar = f"{bar_color}{bar_chars}{DIM}{empty_chars}{R}"
        else:
            bar = f"{bar_color}{bar_chars}{R}"

        text = f"{C_TL}│{R} {DIM}{title_pad}{R} [{bar}] {BOLD}{pct_str}{R} {DIM}•{R} {size_str} {DIM}•{R} {time_str}"
        ui.set_inner(text)

    def done(self) -> None:
        if self._tty:
            self.update(1, 1)
            text = ui.inner_text or ""
            ui.close_inner(text.replace(f"{DIM}{self._title:<15}{R}", f"{BOLD}{self._title:<15}{R}").replace(f"{C_TL}│{R} ", ""))
        else:
            ui.print(f"   Downloading {self._title}... 100% [OK]")
