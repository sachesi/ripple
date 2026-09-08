
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import CONFIG_PATH, DEFAULT_CENTRAL_BASE, detect_cpu_level
from .sources import SOURCES
from .ui import C_TL, CYAN, R, ask, info, ok, step, ui, warn, yn


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
            enabled_sources=list(d.get("enabled_sources", [])),
            manage_umu=bool(d.get("manage_umu", False)),
        )


def load_config() -> Config | None:
    try:
        raw = CONFIG_PATH.read_text()
    except FileNotFoundError:
        return None
    try:
        return Config.from_dict(json.loads(raw))
    except (KeyError, TypeError, ValueError) as exc:
        warn(f"Config at {CONFIG_PATH} could not be read ({exc}).")
        warn("Starting the configuration wizard; saving will overwrite that file.")
        return None


def save_config(cfg: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n")
    ok(f"Config saved to {CYAN}{CONFIG_PATH}{R}")


def run_wizard(existing: Config | None = None) -> Config:
    step("Configuration Wizard")
    cpu_level = detect_cpu_level()
    info(f"{CYAN}CPU{R} microarchitecture level: {CYAN}x86-64-v{cpu_level}{R}\n{C_TL}│{R}")

    default_dir = str(existing.central_base) if existing else str(DEFAULT_CENTRAL_BASE)
    ui.print(f"{C_TL}│{R}  Where should Proton releases be stored?")
    ui.print(f"{C_TL}│{R}  (single real copy — other directories receive symlinks)")
    central_base = Path(ask("Store path", default_dir)).expanduser().resolve()

    ui.print(f"{C_TL}│{R}\n{C_TL}│{R}  Which Proton sources do you want to download?")
    currently_enabled = set(existing.enabled_sources) if existing else set(SOURCES)
    enabled = [
        slug
        for slug, api in SOURCES.items()
        if yn(f"[{slug}] {api.name:<14} ({api.description})", default=slug in currently_enabled)
    ]

    manage_umu = yn("Manage umu-run zipapp in ~/.local/bin", default=existing.manage_umu if existing else False)

    if not enabled and not manage_umu:
        warn("No Proton sources selected and umu management is disabled.")

    cfg = Config(central_base=central_base, enabled_sources=enabled, manage_umu=manage_umu)
    save_config(cfg)
    return cfg
