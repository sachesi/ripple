
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from .archive import safe_extract
from .config import Config
from .constants import (
    UMU_BIN_DIR,
    UMU_BIN_PATH,
    UMU_LATEST_RELEASE_API,
    UMU_RELEASES_API,
    UMU_STATE_DIR,
    UMU_VERSION_FILE,
)
from .http import download_file, fetch_json, iter_releases
from .sources import ReleaseInfo
from .ui import BOLD, C_TL, CYAN, DIM, R, ok, paginate_interactive, step, ui, warn


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
    for rel in iter_releases(UMU_RELEASES_API):
        if rel["tag_name"] != tag:
            continue
        asset_url = _pick_umu_zipapp_url(rel)
        if not asset_url:
            raise RuntimeError(f"Release '{tag}' found but no zipapp asset exists.")
        return ReleaseInfo("UMU Launcher", "umu", tag, asset_url)
    raise RuntimeError(f"Release tag '{tag}' not found for umu.")


def list_remote_umu_releases() -> None:
    step("Remote Releases for umu")
    items = []
    for rel in iter_releases(UMU_RELEASES_API):
        asset_url = _pick_umu_zipapp_url(rel)
        if not asset_url:
            continue
        items.append([
            f"{C_TL}│{R}  {CYAN}{rel['tag_name']}{R}",
            f"{C_TL}│{R}    {DIM}{Path(asset_url).name}{R}"
        ])
    if not items:
        warn("No matching umu zipapp assets found.")
        return
    paginate_interactive(items)


def _extract_umu_binary(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        safe_extract(tf, dest)

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
