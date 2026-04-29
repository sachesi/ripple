from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    ALL_SOURCES,
    CONFIG_PATH,
    DEFAULT_CENTRAL_BASE,
    HOME,
    LATEST_LINK_LABEL,
    LOCK_FILENAME,
    MIN_FREE_SPACE_GB,
    SYMLINK_TARGET_LABELS,
    TIMEOUT,
    UMU_BIN_DIR,
    UMU_BIN_PATH,
    UMU_LATEST_RELEASE_API,
    UMU_RELEASES_API,
    UMU_STATE_DIR,
    UMU_VERSION_FILE,
    detect_cpu_level,
)
from .ui import BOLD, C_TL, CYAN, DIM, GREEN, R, YELLOW, DownloadProgressBar, err, info, ok, step, ui, warn


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


@dataclass
class SourceAPI:
    url: str
    pick_asset: Callable[[str], bool]
    cpu_aware: bool = False


def _require_https_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"Refusing non-HTTPS URL: {url}")


def fetch_json(url: str) -> Any:
    _require_https_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "ripple/3.0.3"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310
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
        tf.extract(member, path=dest)


def download_file(url: str, dest: Path, label: str) -> None:
    _require_https_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "ripple/3.0.3"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(dest, "wb") as out:  # nosec B310
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


def toggle_lock(central_base: Path, spec: str, *, lock: bool) -> None:
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
