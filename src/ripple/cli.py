from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import load_config, run_wizard
from .constants import FLATPAK_TARGET_DIRS, NATIVE_TARGET_DIRS, SYMLINK_TARGET_LABELS
from .sources import fetch_releases_concurrently, fetch_specific_release, list_remote_releases
from .store import (
    install_release,
    link_locked_versions,
    list_installed,
    parse_spec,
    remove_old_versions,
    toggle_lock,
)
from .umu import (
    fetch_specific_umu_release,
    fetch_umu_release,
    install_umu_release,
    list_managed_umu,
    list_remote_umu_releases,
)
from .ui import BOLD, R, done_msg, err, info, ok, step, warn, yn


def _installed_flatpak_ids() -> set[str]:
    if shutil.which("flatpak") is None:
        return set()
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        warn(f"Could not query installed Flatpak applications: {exc}")
        return set()
    return set(result.stdout.splitlines())


def _native_target(candidates: tuple[Path, ...]) -> Path:
    return next(
        (path for path in candidates if path.is_dir()),
        next((path for path in candidates if path.parent.is_dir()), candidates[-1]),
    )


def _flatpak_can_read(app_id: str, path: Path) -> bool:
    try:
        result = subprocess.run(
            ["flatpak", "run", "--command=/usr/bin/test", app_id, "-r", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def _grant_flatpak_access(app_id: str, path: Path) -> bool:
    option = f"--filesystem={path}:ro"
    command = ["flatpak", "override", "--user", option, app_id]
    label = SYMLINK_TARGET_LABELS[FLATPAK_TARGET_DIRS[app_id]]
    prompt = f"Allow {label} read-only access to the Proton store at {path}?"
    if not sys.stdin.isatty() or not yn(prompt, default=False):
        warn(f"Skipping {label}; grant access with: {shlex.join(command)}")
        return False
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        warn(f"Could not grant {label} access: {exc}")
        return False
    if not _flatpak_can_read(app_id, path):
        warn(f"{label} still cannot read the Proton store after applying its Flatpak override.")
        return False
    info(f"Granted {label} read-only access to the Proton store.")
    return True


def prepare_symlink_dirs(central_base: Path) -> list[Path]:
    targets: list[tuple[Path, str | None]] = []
    for command, candidates in NATIVE_TARGET_DIRS.items():
        if shutil.which(command) is not None:
            targets.append((_native_target(candidates), None))

    flatpak_ids = _installed_flatpak_ids()
    targets.extend((path, app_id) for app_id, path in FLATPAK_TARGET_DIRS.items() if app_id in flatpak_ids)

    central_base.mkdir(parents=True, exist_ok=True)
    ready: list[Path] = []
    seen: set[Path] = set()
    for target, app_id in targets:
        resolved = target.resolve()
        if resolved in seen:
            continue
        target.mkdir(parents=True, exist_ok=True)
        if (
            app_id is not None
            and not _flatpak_can_read(app_id, central_base)
            and not _grant_flatpak_access(app_id, central_base)
        ):
            continue
        seen.add(resolved)
        ready.append(target)
    return ready


def require_symlink_dirs(central_base: Path) -> list[Path]:
    try:
        return prepare_symlink_dirs(central_base)
    except OSError as exc:
        raise RuntimeError(f"Could not prepare compatibility-tool directories: {exc}") from exc


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


def _dispatch(args: argparse.Namespace) -> None:
    cfg = load_config()

    if args.list_remote:
        if args.list_remote == "umu":
            list_remote_umu_releases()
        else:
            list_remote_releases(args.list_remote)
        done_msg("Listed remote releases.")
        return

    if cfg is None or args.configure:
        cfg = run_wizard(existing=cfg)

    if args.list:
        list_installed(cfg)
        list_managed_umu(cfg)
        done_msg("Listed installed versions.")
        return

    if args.lock:
        toggle_lock(cfg.central_base, args.lock, lock=True)
        link_locked_versions(cfg.central_base, require_symlink_dirs(cfg.central_base))
        done_msg("Lock applied.")
        return
    if args.unlock:
        toggle_lock(cfg.central_base, args.unlock, lock=False)
        done_msg("Lock removed.")
        return

    if args.remove_old:
        remove_old_versions(cfg, require_symlink_dirs(cfg.central_base))
        done_msg("Cleanup complete.")
        return

    if args.download:
        dl_slug, dl_tag = parse_spec(args.download)
        if dl_slug == "umu":
            install_umu_release(fetch_specific_umu_release(dl_tag))
        else:
            symlink_dirs = require_symlink_dirs(cfg.central_base)
            install_release(fetch_specific_release(dl_slug, dl_tag), cfg.central_base, symlink_dirs, update_latest=False)
            link_locked_versions(cfg.central_base, symlink_dirs)
        done_msg("Download complete.")
        return

    if not cfg.enabled_sources and not cfg.manage_umu:
        warn(f"Nothing to do. Run {BOLD}ripple --configure{R} to enable Proton sources and/or umu.")
        sys.exit(0)

    symlink_dirs = require_symlink_dirs(cfg.central_base)
    results = fetch_releases_concurrently(cfg.enabled_sources) if cfg.enabled_sources else {}

    for slug in cfg.enabled_sources:
        step(f"Processing {BOLD}{slug}{R}")
        rel = results.get(slug)
        if isinstance(rel, Exception):
            warn(f"Fetch failed: {rel}")
            continue
        if rel is None:
            warn(f"'{slug}' is not a known source; skipping.")
            continue
        try:
            install_release(rel, cfg.central_base, symlink_dirs)
        except Exception as exc:
            warn(f"Installation failed: {exc}")

    step("Locked Proton versions")
    has_locked_versions, linked_any = link_locked_versions(cfg.central_base, symlink_dirs)
    if not has_locked_versions:
        info("No locked versions configured.")
    elif not linked_any:
        ok("Already up to date.")

    if cfg.manage_umu:
        step(f"Processing {BOLD}umu{R}")
        try:
            install_umu_release(fetch_umu_release())
        except Exception as exc:
            warn(f"UMU installation failed: {exc}")

    done_msg("Update run complete.")


def main() -> None:
    args = build_parser().parse_args()
    try:
        _dispatch(args)
    except Exception as exc:
        err(str(exc))
        sys.exit(1)
