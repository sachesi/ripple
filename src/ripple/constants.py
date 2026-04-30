from __future__ import annotations

from pathlib import Path

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

ALL_SOURCES: list[tuple[str, str]] = [
    ("ge-proton", "GE Proton      (GloriousEggroll/proton-ge-custom, GitHub)"),
    ("dw-proton", "DW Proton      (dawn-winery/dwproton, dawn.wine)"),
    (
        "cachyos-proton",
        "CachyOS Proton (CachyOS/proton-cachyos, GitHub) — auto-selects v2/v3/v4 build",
    ),
    ("em-proton", "EM Proton      (Etaash-mathamsetty/Proton, GitHub)"),
]

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
