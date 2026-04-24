from __future__ import annotations

import argparse
import sys

from .constants import SYMLINK_TARGET_DIRS
from .core import (
    fetch_releases_concurrently,
    fetch_specific_release,
    fetch_specific_umu_release,
    fetch_umu_release,
    install_release,
    install_umu_release,
    link_locked_versions,
    list_installed,
    list_managed_umu,
    list_remote_releases,
    list_remote_umu_releases,
    load_config,
    remove_old_versions,
    run_wizard,
    toggle_lock,
)
from .ui import BOLD, R, done_msg, err, info, step, warn


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
        toggle_lock(cfg.central_base, args.lock, lock=True)
        link_locked_versions(cfg.central_base, existing_symlink_dirs)
        done_msg("Done.")
        return
    if args.unlock:
        toggle_lock(cfg.central_base, args.unlock, lock=False)
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
        except Exception as exc:
            warn(f"Installation failed: {exc}")

    step("Locked Proton versions")
    has_locked_versions, linked_any = link_locked_versions(cfg.central_base, existing_symlink_dirs)
    if not has_locked_versions:
        info("No locked versions configured.")
    elif not linked_any:
        from .ui import ok

        ok("Already up to date.")

    if cfg.manage_umu:
        step(f"Processing {BOLD}umu{R}")
        try:
            install_umu_release(fetch_umu_release())
        except Exception as exc:
            warn(f"UMU installation failed: {exc}")

    done_msg("All configured tools are up-to-date.")
