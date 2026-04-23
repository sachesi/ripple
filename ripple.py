#!/usr/bin/env python3
"""ripple — download and install the latest Proton releases."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIMEOUT = 30
MIN_FREE_SPACE_GB = 2
HOME = Path.home()
CONFIG_PATH = HOME / ".config" / "ripple" / "config.json"
LOCK_FILENAME = ".locked"
DEFAULT_CENTRAL_BASE = HOME / ".local/share/ripple/store"

UMU_BIN_DIR = HOME / ".local" / "bin"
UMU_BIN_PATH = UMU_BIN_DIR / "umu-run"
UMU_STATE_DIR = HOME / ".local" / "share" / "ripple" / "umu"
UMU_VERSION_FILE = UMU_STATE_DIR / ".latest-version"

UMU_LATEST_RELEASE_API = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
UMU_RELEASES_API = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases"

SYMLINK_TARGET_DIRS: list[Path] = [
    HOME / ".var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d",
    HOME / ".var/app/com.usebottles.bottles/data/bottles/runners",
    HOME / ".var/app/net.lutris.Lutris/data/lutris/runners/wine",
    HOME / ".local/share/Steam/compatibilitytools.d",
    HOME / ".local/share/bottles/data/bottles/runners",
    HOME / ".local/share/lutris/runners/wine",
    HOME / ".local/share/leyen/proton",
]

SYMLINK_TARGET_LABELS: dict[Path, str] = {
    HOME / ".var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d": "Steam Flatpak",
    HOME / ".var/app/com.usebottles.bottles/data/bottles/runners": "Bottles Flatpak",
    HOME / ".var/app/net.lutris.Lutris/data/lutris/runners/wine": "Lutris Flatpak",
    HOME / ".local/share/Steam/compatibilitytools.d": "Steam Native",
    HOME / ".local/share/bottles/data/bottles/runners": "Bottles Native",
    HOME / ".local/share/lutris/runners/wine": "Lutris Native",
    HOME / ".local/share/leyen/proton": "Leyen",
}

LATEST_LINK_LABEL = "Store latest alias"

ALL_SOURCES: list[tuple[str, str]] = [
    ("ge-proton", "GE Proton      (GloriousEggroll/proton-ge-custom, GitHub)"),
    ("dw-proton", "DW Proton      (dawn-winery/dwproton, dawn.wine)"),
    (
        "cachyos-proton",
        "CachyOS Proton (CachyOS/proton-cachyos, GitHub) — auto-selects v2/v3/v4 build",
    ),
    ("em-proton", "EM Proton      (Etaash-mathamsetty/Proton, GitHub)"),
]

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


_V2_FLAGS = {"cx16", "lahf_lm", "popcnt", "sse4_1", "sse4_2", "ssse3"}
_V3_FLAGS = {"avx", "avx2", "bmi1", "bmi2", "fma", "movbe", "xsave"}
_V4_FLAGS = {"avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"}


def detect_cpu_level() -> int:
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        flags: set[str] = set()
        for line in cpuinfo.splitlines():
            if line.startswith("flags"):
                flags.update(line.split(":", 1)[1].split())
        if _V4_FLAGS.issubset(flags):
            return 4
        if _V3_FLAGS.issubset(flags):
            return 3
        if _V2_FLAGS.issubset(flags):
            return 2
        return 1
    except Exception:
        return 1


@dataclass
class Config:
    central_base: Path
    enabled_sources: list[str]
    manage_umu: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "central_base": str(self.central_base),
            "enabled_sources": self.enabled_sources,
            "manage_umu": self.manage_umu,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Config":
        return cls(
            central_base=Path(d["central_base"]),
            enabled_sources=d["enabled_sources"],
            manage_umu=bool(d.get("manage_umu", False)),
        )


def load_config() -> Config | None:
    try:
        return Config.from_dict(json.loads(CONFIG_PATH.read_text()))
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def save_config(cfg: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n")
    ok(f"Config saved to {CYAN}{CONFIG_PATH}{R}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{C_TL}│{R}  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value if value else default


def yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = ask(f"{prompt} ({hint})")
    if not raw:
        return default
    return raw.lower().startswith("y")


def run_wizard(existing: Config | None = None) -> Config:
    step("Configuration Wizard")
    cpu_level = detect_cpu_level()
    info(f"{CYAN}CPU{R} microarchitecture level: {CYAN}x86-64-v{cpu_level}{R}\n{C_TL}│{R}")

    default_dir = str(existing.central_base) if existing else str(DEFAULT_CENTRAL_BASE)
    ui.print(f"{C_TL}│{R}  Where should Proton releases be stored?")
    ui.print(f"{C_TL}│{R}  (single real copy — other directories receive symlinks)")
    central_base = Path(ask("Store path", default_dir)).expanduser().resolve()

    ui.print(f"{C_TL}│{R}\n{C_TL}│{R}  Which Proton sources do you want to download?")
    currently_enabled = set(existing.enabled_sources) if existing else {s for s, _ in ALL_SOURCES}
    enabled = [slug for slug, label in ALL_SOURCES if yn(f"[{slug}] {label}", default=slug in currently_enabled)]

    manage_umu = yn("Manage umu-run zipapp in ~/.local/bin", default=existing.manage_umu if existing else False)

    if not enabled and not manage_umu:
        warn("No Proton sources selected and umu management is disabled.")

    cfg = Config(central_base=central_base, enabled_sources=enabled, manage_umu=manage_umu)
    save_config(cfg)
    return cfg


@dataclass
class ReleaseInfo:
    name: str
    slug: str
    tag: str
    asset_url: str


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "ripple/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(f"API Rate Limit exceeded (403) for {url}") from e
        raise RuntimeError(f"Server returned error {e.code} for {url}") from e


def fetch_json_paged(url: str, *, per_page: int = 100) -> list[Any]:
    results: list[Any] = []
    page = 1
    sep = "&" if "?" in url else "?"
    while True:
        batch = fetch_json(f"{url}{sep}per_page={per_page}&page={page}")
        if not batch:
            break
        results.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return results


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    if hasattr(tarfile, "fully_trusted_filter"):
        tf.extractall(path=dest, filter="data")
        return
    resolved_dest = dest.resolve()
    for member in tf.getmembers():
        member_target = (dest / member.name).resolve()
        if not _is_within(resolved_dest, member_target):
            raise RuntimeError(f"Unsafe archive member path: {member.name}")
    tf.extractall(path=dest)


def download_file(url: str, dest: Path, label: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "ripple/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            pb = DownloadProgressBar(label)
            chunks = 0
            while data := resp.read(1 << 17):
                out.write(data)
                downloaded += len(data)
                chunks += 1
                pb.update(downloaded, total, chunks)
            pb.done()
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def extract_archive(archive: Path, dest: Path) -> Path:
    info(f"Extracting {archive.name} ...")
    with tarfile.open(archive) as tf:
        top_dirs = {Path(m.name).parts[0] for m in tf.getmembers() if m.name}
        _safe_extract(tf, dest)

    if len(top_dirs) == 1:
        return dest / top_dirs.pop()
    subdirs = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(subdirs) == 1:
        return subdirs[0]
    raise RuntimeError(f"Cannot determine extracted root folder. Found: {[p.name for p in subdirs]}")


def _symlink_display_names(link_path: Path, target: Path, destination_label: str | None = None) -> tuple[str, str]:
    if destination_label is None:
        return link_path.name, target.name
    source_name = target.name if link_path.name == target.name else link_path.name
    return source_name, destination_label


def make_symlink(link_path: Path, target: Path, verbose: bool = True, destination_label: str | None = None) -> None:
    shown_source, shown_dest = _symlink_display_names(link_path, target, destination_label)

    if link_path.is_symlink():
        if link_path.resolve() == target.resolve():
            return
        if verbose:
            info(f"Relink: {shown_source} {DIM}→{R} {shown_dest}")
        link_path.unlink()
    elif link_path.exists():
        if verbose:
            warn(f"Directory exists where symlink is needed:\n{C_TL}│{R}    {DIM}{link_path}{R}\n{C_TL}│{R}  Target would be: {DIM}{target}{R}")
        if sys.stdin.isatty() and yn(f"Remove '{link_path.name}' and replace with symlink?", default=False):
            if link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
            ok(f"Removed: {DIM}{link_path}{R}")
        else:
            warn(f"Non-interactive or declined, skipping: {DIM}{str(link_path)}{R}")
            return
    else:
        if verbose:
            info(f"Link:   {shown_source} {DIM}→{R} {shown_dest}")
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target)


def fetch_ge_proton() -> ReleaseInfo:
    for rel in fetch_json("https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"):
        for asset in rel.get("assets", []):
            url = asset["browser_download_url"]
            if url.endswith(".tar.gz"):
                return ReleaseInfo("GE Proton", "ge-proton", rel["tag_name"], url)
    raise RuntimeError("No GE Proton release with a .tar.gz asset found.")


def fetch_dw_proton() -> ReleaseInfo:
    for rel in fetch_json("https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases"):
        for asset in rel.get("assets", []):
            url = asset["browser_download_url"]
            if url.endswith((".tar.xz", ".tar.gz")):
                return ReleaseInfo("DW Proton", "dw-proton", rel["tag_name"], url)
    raise RuntimeError("No DW Proton release with a .tar.xz / .tar.gz asset found.")


def fetch_cachyos_proton() -> ReleaseInfo:
    cpu_level = detect_cpu_level()
    releases = fetch_json("https://api.github.com/repos/CachyOS/proton-cachyos/releases")
    suffixes_by_priority = ["x86_64"]
    if cpu_level >= 2:
        suffixes_by_priority.insert(0, "x86_64_v2")
    if cpu_level >= 3:
        suffixes_by_priority.insert(0, "x86_64_v3")
    if cpu_level >= 4:
        suffixes_by_priority.insert(0, "x86_64_v4")

    for rel in releases:
        suffix_map: dict[str, str] = {}
        for asset in rel.get("assets", []):
            url = asset["browser_download_url"]
            if not url.endswith((".tar.xz", ".tar.gz")):
                continue
            for sfx in suffixes_by_priority:
                if re.search(rf"-{re.escape(sfx)}\.(tar\.xz|tar\.gz)$", url):
                    suffix_map[sfx] = url
                    break
        for sfx in suffixes_by_priority:
            if sfx in suffix_map:
                return ReleaseInfo("CachyOS Proton", "cachyos-proton", rel["tag_name"], suffix_map[sfx])
    raise RuntimeError("No CachyOS Proton release found matching this CPU's architecture level.")


def fetch_em_proton() -> ReleaseInfo:
    for rel in fetch_json("https://api.github.com/repos/Etaash-mathamsetty/Proton/releases"):
        for asset in rel.get("assets", []):
            url = asset["browser_download_url"]
            if url.endswith((".tar.xz", ".tar.gz")):
                return ReleaseInfo("EM Proton", "em-proton", rel["tag_name"], url)
    raise RuntimeError("No EM Proton release with a .tar.xz / .tar.gz asset found.")


FETCHERS: dict[str, Callable[[], ReleaseInfo]] = {
    "ge-proton": fetch_ge_proton,
    "dw-proton": fetch_dw_proton,
    "cachyos-proton": fetch_cachyos_proton,
    "em-proton": fetch_em_proton,
}


@dataclass
class SourceAPI:
    url: str
    pick_asset: Callable[[str], bool]
    cpu_aware: bool = False


def _cachyos_asset_filter(url: str) -> bool:
    cpu_level = detect_cpu_level()
    suffixes = ["x86_64"]
    if cpu_level >= 2:
        suffixes.insert(0, "x86_64_v2")
    if cpu_level >= 3:
        suffixes.insert(0, "x86_64_v3")
    if cpu_level >= 4:
        suffixes.insert(0, "x86_64_v4")
    return url.endswith((".tar.xz", ".tar.gz")) and any(re.search(rf"-{re.escape(sfx)}\.(tar\.xz|tar\.gz)$", url) for sfx in suffixes)


RELEASE_APIS: dict[str, SourceAPI] = {
    "ge-proton": SourceAPI("https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases", lambda u: u.endswith(".tar.gz")),
    "dw-proton": SourceAPI("https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases", lambda u: u.endswith((".tar.xz", ".tar.gz"))),
    "cachyos-proton": SourceAPI("https://api.github.com/repos/CachyOS/proton-cachyos/releases", _cachyos_asset_filter, True),
    "em-proton": SourceAPI("https://api.github.com/repos/Etaash-mathamsetty/Proton/releases", lambda u: u.endswith((".tar.xz", ".tar.gz"))),
}


def fetch_releases_concurrently(slugs: list[str]) -> dict[str, Any]:
    step("Checking for updates")
    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(slugs))) as executor:
        futs = {executor.submit(FETCHERS[s]): s for s in slugs if s in FETCHERS}
        for fut in concurrent.futures.as_completed(futs):
            slug = futs[fut]
            try:
                results[slug] = fut.result()
            except Exception as e:
                results[slug] = e
    return results


def install_release(release: ReleaseInfo, central_base: Path, symlink_dirs: list[Path], *, update_latest: bool = True) -> None:
    store_dir = central_base / "crate" / release.slug
    central_dir = store_dir / release.tag
    version_file = store_dir / ".latest-version"

    if central_dir.is_dir():
        locked = (central_dir / LOCK_FILENAME).exists()
        lock_note = " 🔒 locked" if locked else ""
        if update_latest and version_file.exists() and version_file.read_text().strip() == release.tag:
            ok(f"Already up to date: {DIM}{release.tag}{R}{lock_note}")
        else:
            ok(f"Already stored: {DIM}{central_dir.name}{R}{lock_note}")
    else:
        _, _, free = shutil.disk_usage(central_base.parent if central_base.parent.exists() else HOME)
        if free < (MIN_FREE_SPACE_GB * 1024**3):
            warn(f"Low disk space ({free / 1024**3:.1f} GB free).")

        store_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=store_dir, prefix=".tmp_") as tmp_str:
            tmp = Path(tmp_str)
            archive_path = tmp / Path(release.asset_url).name
            download_file(release.asset_url, archive_path, release.name)
            extracted_root = extract_archive(archive_path, tmp)
            info(f"Moving to store: {DIM}{central_dir.name}{R}")
            extracted_root.rename(central_dir)
            ok(f"Installed {release.name} {release.tag}")

    if update_latest:
        version_file.write_text(release.tag + "\n")
        make_symlink(central_base / f"{release.slug}-latest", central_dir, destination_label=LATEST_LINK_LABEL)
    else:
        info("Pinned install - latest pointer unchanged")

    for parent_dir in symlink_dirs:
        if parent_dir.is_dir():
            make_symlink(parent_dir / release.tag, central_dir, destination_label=SYMLINK_TARGET_LABELS.get(parent_dir, str(parent_dir)))


def link_locked_versions(central_base: Path, symlink_dirs: list[Path]) -> tuple[bool, bool]:
    crate_dir = central_base / "crate"
    if not crate_dir.is_dir():
        return False, False
    has_locked_versions = False
    linked_any = False
    for slug_dir in crate_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        for ver_dir in slug_dir.iterdir():
            if ver_dir.is_dir() and (ver_dir / LOCK_FILENAME).exists():
                has_locked_versions = True
                for parent_dir in symlink_dirs:
                    if parent_dir.is_dir():
                        link_path = parent_dir / ver_dir.name
                        if not link_path.is_symlink() or link_path.resolve() != ver_dir.resolve():
                            if not linked_any:
                                info("Linking missing locked versions...")
                                linked_any = True
                            make_symlink(link_path, ver_dir, destination_label=SYMLINK_TARGET_LABELS.get(parent_dir, str(parent_dir)))
    return has_locked_versions, linked_any


def remove_old_versions(cfg: Config, symlink_dirs: list[Path]) -> None:
    step("Cleaning Up Old Versions")
    crate_dir = cfg.central_base / "crate"
    if not crate_dir.is_dir():
        info("Store is empty, nothing to remove.")
        return

    removed_count = 0
    total_freed = 0
    for slug_dir in crate_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        latest_tag = (slug_dir / ".latest-version").read_text().strip() if (slug_dir / ".latest-version").exists() else None

        old_dirs: list[Path] = []
        for item in slug_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                if item.name == latest_tag:
                    continue
                if (item / LOCK_FILENAME).exists():
                    info(f"Keeping locked version: {slug_dir.name}/{item.name}")
                    continue
                old_dirs.append(item)

        for old_dir in sorted(old_dirs):
            size = sum(f.stat().st_size for f in old_dir.rglob("*") if f.is_file())
            total_freed += size
            info(f"Removing {slug_dir.name}/{old_dir.name} {DIM}({size / 1_048_576:.0f} MiB){R}")
            shutil.rmtree(old_dir, ignore_errors=True)
            removed_count += 1

    dangling_count = 0
    for sym_dir in symlink_dirs:
        if not sym_dir.is_dir():
            continue
        for link in sym_dir.iterdir():
            if link.is_symlink() and not link.exists():
                info(f"Removing dangling symlink: {link.name}")
                link.unlink()
                dangling_count += 1

    if removed_count == 0 and dangling_count == 0:
        ok("No old versions or dangling symlinks to remove.")
    else:
        gib = total_freed / 1_073_741_824
        mib = total_freed / 1_048_576
        size_str = f"{gib:.2f} GiB" if total_freed >= 1_073_741_824 else f"{mib:.0f} MiB"
        ok(f"Removed {removed_count} old versions. Freed {GREEN}~{size_str}{R}.")
        if dangling_count:
            ok(f"Cleaned {dangling_count} broken symlinks.")


def _pick_umu_zipapp_url(rel: dict[str, Any]) -> str | None:
    for asset in rel.get("assets", []):
        url = asset["browser_download_url"]
        if url.endswith("-zipapp.tar"):
            return url
    return None


def fetch_umu_release() -> ReleaseInfo:
    rel = fetch_json(UMU_LATEST_RELEASE_API)
    asset_url = _pick_umu_zipapp_url(rel)
    if not asset_url:
        raise RuntimeError("No umu-launcher zipapp asset found in the latest release.")
    return ReleaseInfo("UMU Launcher", "umu", rel["tag_name"], asset_url)


def fetch_specific_umu_release(tag: str) -> ReleaseInfo:
    for rel in fetch_json_paged(UMU_RELEASES_API):
        if rel["tag_name"] != tag:
            continue
        asset_url = _pick_umu_zipapp_url(rel)
        if not asset_url:
            raise RuntimeError(f"Release '{tag}' found but no zipapp asset exists.")
        return ReleaseInfo("UMU Launcher", "umu", tag, asset_url)
    raise RuntimeError(f"Release tag '{tag}' not found for umu.")


def list_remote_umu_releases() -> None:
    step("Remote Releases for umu")
    shown = 0
    for rel in fetch_json_paged(UMU_RELEASES_API):
        asset_url = _pick_umu_zipapp_url(rel)
        if not asset_url:
            continue
        ui.print(f"{C_TL}│{R}  {CYAN}{rel['tag_name']}{R}")
        ui.print(f"{C_TL}│{R}    {DIM}{Path(asset_url).name}{R}")
        shown += 1
    if shown == 0:
        warn("No matching umu zipapp assets found.")


def _extract_umu_binary(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        _safe_extract(tf, dest)

    candidates = [p for p in dest.rglob("umu-run") if p.is_file()]
    if not candidates:
        raise RuntimeError(f"Could not find extracted umu-run in {archive.name}")

    exec_candidates = [p for p in candidates if os.access(p, os.X_OK)]
    return exec_candidates[0] if exec_candidates else candidates[0]


def _warn_if_umu_bin_dir_missing_from_path() -> None:
    path_parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    expanded_parts = {Path(p).expanduser().resolve() for p in path_parts}
    if UMU_BIN_DIR.resolve() not in expanded_parts:
        warn(
            "umu-run is installed, but ~/.local/bin is not in PATH. "
            f"Run it directly as {DIM}{UMU_BIN_PATH}{R} or add it to PATH "
            "(fish example: fish_add_path ~/.local/bin)."
        )


def install_umu_release(release: ReleaseInfo) -> None:
    current_tag = UMU_VERSION_FILE.read_text().strip() if UMU_VERSION_FILE.exists() else None

    if UMU_BIN_PATH.exists() and current_tag == release.tag:
        ok(f"umu-run is already up to date: {DIM}{release.tag}{R}")
        _warn_if_umu_bin_dir_missing_from_path()
        return

    UMU_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=UMU_STATE_DIR, prefix=".tmp_umu_") as tmp_str:
        tmp = Path(tmp_str)
        archive_path = tmp / Path(release.asset_url).name
        extract_dir = tmp / "extract"

        download_file(release.asset_url, archive_path, release.name)
        extracted_bin = _extract_umu_binary(archive_path, extract_dir)

        UMU_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tmp_target = UMU_BIN_DIR / ".umu-run.tmp"
        shutil.copy2(extracted_bin, tmp_target)
        tmp_target.chmod(0o755)
        tmp_target.replace(UMU_BIN_PATH)

    UMU_VERSION_FILE.write_text(release.tag + "\n")
    ok(f"Installed umu-run {release.tag} to {CYAN}{UMU_BIN_PATH}{R}")
    _warn_if_umu_bin_dir_missing_from_path()


def list_managed_umu(cfg: Config) -> None:
    if not cfg.manage_umu:
        return
    step("Managed UMU")
    if not UMU_BIN_PATH.exists():
        warn("umu-run is not installed.")
        return

    version = UMU_VERSION_FILE.read_text().strip() if UMU_VERSION_FILE.exists() else "unknown"
    ui.print(f"{C_TL}│{R}  {CYAN}[umu]{R}  {BOLD}UMU Launcher{R}")
    ui.print(f"{C_TL}│{R}    {CYAN}{version}{R}")
    ui.print(f"{C_TL}│{R}    {DIM}{UMU_BIN_PATH}{R}")


def list_installed(cfg: Config) -> None:
    step("Installed Versions")
    crate_dir = cfg.central_base / "crate"
    any_found = False
    for slug, label in ALL_SOURCES:
        store_dir = crate_dir / slug
        if not store_dir.is_dir():
            continue
        latest_tag = (cfg.central_base / f"{slug}-latest").resolve().name if (cfg.central_base / f"{slug}-latest").is_symlink() else None
        versions = sorted([p for p in store_dir.iterdir() if p.is_dir() and not p.name.startswith(".")], reverse=True)
        if not versions:
            continue
        any_found = True
        ui.print(f"{C_TL}│{R}  {CYAN}[{slug}]{R}  {BOLD}{label.split('(')[0].strip()}{R}")
        for v in versions:
            markers = []
            if v.name == latest_tag:
                markers.append(GREEN + "latest" + R)
            if (v / LOCK_FILENAME).exists():
                markers.append(YELLOW + "locked" + R)
            tag_str = f"{C_TL}│{R}    " + (CYAN + v.name + R if v.name == latest_tag else v.name)
            if markers:
                tag_str += "  " + DIM + "← " + R + ", ".join(markers)
            ui.print(tag_str)
        ui.print(f"{C_TL}│{R}")
    if not any_found:
        warn("No versions installed yet.")


def list_remote_releases(slug: str) -> None:
    step(f"Remote Releases for {slug}")
    api = RELEASE_APIS.get(slug)
    if api is None:
        err(f"Unknown slug '{slug}'. Valid slugs: {', '.join(RELEASE_APIS)}")
        sys.exit(1)
    if api.cpu_aware:
        info(f"CPU x86-64-v{detect_cpu_level()} - showing best asset per release")
    shown = 0
    for rel in fetch_json_paged(api.url):
        asset_url = next((a["browser_download_url"] for a in rel.get("assets", []) if api.pick_asset(a["browser_download_url"])), None)
        if asset_url:
            ui.print(f"{C_TL}│{R}  {CYAN}{rel['tag_name']}{R}")
            ui.print(f"{C_TL}│{R}    {DIM}{Path(asset_url).name}{R}")
            shown += 1
    if shown == 0:
        warn("No matching assets found.")


def fetch_specific_release(slug: str, tag: str) -> ReleaseInfo:
    step(f"Fetching specific release: {slug} {tag}")
    api = RELEASE_APIS.get(slug)
    if api is None:
        raise RuntimeError(f"Unknown slug '{slug}'. Valid slugs: {', '.join(RELEASE_APIS)}")
    name = {s: lbl.split("(")[0].strip() for s, lbl in ALL_SOURCES}.get(slug, slug)
    for rel in fetch_json_paged(api.url):
        if rel["tag_name"] != tag:
            continue
        asset_url = next((a["browser_download_url"] for a in rel.get("assets", []) if api.pick_asset(a["browser_download_url"])), None)
        if asset_url:
            info(f"Found {CYAN}{tag}{R}")
            return ReleaseInfo(name=name, slug=slug, tag=tag, asset_url=asset_url)
        raise RuntimeError(f"Release '{tag}' found but no matching asset for this CPU.")
    raise RuntimeError(f"Release tag '{tag}' not found for slug '{slug}'.")


def _toggle_lock(central_base: Path, spec: str, *, lock: bool) -> None:
    step(f"{'Locking' if lock else 'Unlocking'} Version")
    if ":" not in spec:
        err(f"Expected SLUG:TAG format, got '{spec}'")
        sys.exit(1)
    slug, tag = spec.split(":", 1)
    version_dir = central_base / "crate" / slug / tag
    if not version_dir.is_dir():
        err(f"Version directory not found: {version_dir}")
        sys.exit(1)
    lock_file = version_dir / LOCK_FILENAME
    if lock:
        lock_file.touch()
        ok(f"Locked: {DIM}{version_dir}{R}")
    elif lock_file.exists():
        lock_file.unlink()
        ok(f"Unlocked: {DIM}{version_dir}{R}")
    else:
        info(f"Already unlocked: {DIM}{version_dir}{R}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ripple", description="Download and install the latest Proton releases.")
    parser.add_argument("--configure", action="store_true", help="Re-run the interactive configuration wizard.")
    parser.add_argument("--remove-old", action="store_true", help="Remove all old Proton versions from the central store, keeping only the latest and locked.")
    parser.add_argument("--lock", metavar="SLUG:TAG", help="Lock a specific version. Format: ge-proton:GE-Proton10-20")
    parser.add_argument("--unlock", metavar="SLUG:TAG", help="Unlock a previously locked version.")
    parser.add_argument("--list", action="store_true", help="List all installed Proton versions in the central store.")
    parser.add_argument("--list-remote", metavar="SLUG", help="List available upstream releases for a slug, e.g. ge-proton or umu")
    parser.add_argument("--download", metavar="SLUG:TAG", help="Download and install a specific version, e.g. ge-proton:TAG or umu:TAG")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    cfg = load_config()

    if args.list_remote:
        if args.list_remote == "umu":
            list_remote_umu_releases()
        else:
            list_remote_releases(args.list_remote)
        done_msg("Done.")
        return

    if cfg is None or args.configure:
        cfg = run_wizard(existing=cfg)

    existing_symlink_dirs = [d for d in SYMLINK_TARGET_DIRS if d.is_dir()]

    if args.list:
        list_installed(cfg)
        list_managed_umu(cfg)
        done_msg("Done.")
        return

    if args.lock:
        _toggle_lock(cfg.central_base, args.lock, lock=True)
        link_locked_versions(cfg.central_base, existing_symlink_dirs)
        done_msg("Done.")
        return
    if args.unlock:
        _toggle_lock(cfg.central_base, args.unlock, lock=False)
        done_msg("Done.")
        return

    if args.remove_old:
        remove_old_versions(cfg, existing_symlink_dirs)
        done_msg("Done.")
        return

    if args.download:
        if ":" not in args.download:
            err(f"Expected SLUG:TAG format, got '{args.download}'")
            sys.exit(1)
        dl_slug, dl_tag = args.download.split(":", 1)
        try:
            if dl_slug == "umu":
                install_umu_release(fetch_specific_umu_release(dl_tag))
            else:
                install_release(fetch_specific_release(dl_slug, dl_tag), cfg.central_base, existing_symlink_dirs, update_latest=False)
                link_locked_versions(cfg.central_base, existing_symlink_dirs)
        except Exception as exc:
            err(str(exc))
            sys.exit(1)
        done_msg("Done.")
        return

    if not cfg.enabled_sources and not cfg.manage_umu:
        warn(f"Nothing to do. Run {BOLD}ripple --configure{R} to enable Proton sources and/or umu.")
        sys.exit(0)

    results = fetch_releases_concurrently(cfg.enabled_sources) if cfg.enabled_sources else {}

    for slug in cfg.enabled_sources:
        step(f"Processing {BOLD}{slug}{R}")
        rel = results.get(slug)
        if isinstance(rel, Exception):
            warn(f"Fetch failed: {rel}")
            continue
        if not rel:
            warn("No release information found.")
            continue
        try:
            install_release(rel, cfg.central_base, existing_symlink_dirs)
        except Exception as e:
            warn(f"Installation failed: {e}")

    step("Locked Proton versions")
    has_locked_versions, linked_any = link_locked_versions(cfg.central_base, existing_symlink_dirs)
    if not has_locked_versions:
        info("No locked versions configured.")
    elif not linked_any:
        ok("Already up to date.")

    if cfg.manage_umu:
        step(f"Processing {BOLD}umu{R}")
        try:
            install_umu_release(fetch_umu_release())
        except Exception as e:
            warn(f"UMU installation failed: {e}")

    done_msg("All configured tools are up-to-date.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write("\r\033[2K")
        sys.exit(130)
