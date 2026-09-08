
import functools
import os
from pathlib import Path

TIMEOUT = 30
MIN_FREE_SPACE_GB = 2
HOME = Path.home()
_xdg_data_home = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")).expanduser()
XDG_DATA_HOME = _xdg_data_home if _xdg_data_home.is_absolute() else HOME / ".local/share"
CONFIG_PATH = HOME / ".config" / "ripple" / "config.json"
LOCK_FILENAME = ".locked"
DEFAULT_CENTRAL_BASE = HOME / ".local/share/ripple/store"

UMU_BIN_DIR = HOME / ".local" / "bin"
UMU_BIN_PATH = UMU_BIN_DIR / "umu-run"
UMU_STATE_DIR = HOME / ".local" / "share" / "ripple" / "umu"
UMU_VERSION_FILE = UMU_STATE_DIR / ".latest-version"

UMU_LATEST_RELEASE_API = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
UMU_RELEASES_API = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases"

NATIVE_TARGET_DIRS: dict[str, tuple[Path, ...]] = {
    "steam": (
        HOME / ".steam/root/compatibilitytools.d",
        HOME / ".steam/steam/compatibilitytools.d",
        XDG_DATA_HOME / "Steam/compatibilitytools.d",
    ),
    "bottles": (XDG_DATA_HOME / "bottles/runners",),
    "lutris": (XDG_DATA_HOME / "lutris/runners/wine",),
    "leyen": (XDG_DATA_HOME / "leyen/proton",),
}

FLATPAK_TARGET_DIRS: dict[str, Path] = {
    "com.valvesoftware.Steam": HOME / ".var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d",
    "com.usebottles.bottles": HOME / ".var/app/com.usebottles.bottles/data/bottles/runners",
    "net.lutris.Lutris": HOME / ".var/app/net.lutris.Lutris/data/lutris/runners/wine",
    "com.github.sachesi.leyen": HOME / ".var/app/com.github.sachesi.leyen/data/leyen/proton",
}

SYMLINK_TARGET_LABELS: dict[Path, str] = {
    HOME / ".var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d": "Steam Flatpak",
    HOME / ".var/app/com.usebottles.bottles/data/bottles/runners": "Bottles Flatpak",
    HOME / ".var/app/net.lutris.Lutris/data/lutris/runners/wine": "Lutris Flatpak",
    HOME / ".var/app/com.github.sachesi.leyen/data/leyen/proton": "Leyen Flatpak",
    HOME / ".steam/root/compatibilitytools.d": "Steam Native",
    HOME / ".steam/steam/compatibilitytools.d": "Steam Native",
    XDG_DATA_HOME / "Steam/compatibilitytools.d": "Steam Native",
    XDG_DATA_HOME / "bottles/runners": "Bottles Native",
    XDG_DATA_HOME / "lutris/runners/wine": "Lutris Native",
    XDG_DATA_HOME / "leyen/proton": "Leyen Native",
}

_V2_FLAGS = {"cx16", "lahf_lm", "popcnt", "sse4_1", "sse4_2", "ssse3"}
_V3_FLAGS = {"avx", "avx2", "bmi1", "bmi2", "fma", "movbe", "xsave"}
_V4_FLAGS = {"avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl"}


@functools.cache
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
