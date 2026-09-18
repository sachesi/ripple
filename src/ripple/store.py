
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .archive import extract_archive, is_within
from .config import Config
from .constants import HOME, LOCK_FILENAME, MIN_FREE_SPACE_GB, SYMLINK_TARGET_LABELS
from .http import download_file
from .sources import SOURCES, ReleaseInfo
from .ui import BOLD, C_TL, CYAN, DIM, GREEN, R, YELLOW, info, ok, step, ui, warn, yn


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


def _latest_tag(slug_dir: Path) -> str | None:
    version_file = slug_dir / ".latest-version"
    return version_file.read_text().strip() if version_file.exists() else None


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _link_target(link: Path) -> Path:
    target = Path(os.readlink(link))
    if not target.is_absolute():
        target = link.parent / target
    return Path(os.path.normpath(target))


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
            ok(f"Already in the store, relinking: {DIM}{central_dir.name}{R}{lock_note}")
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
        make_symlink(central_base / f"{release.slug}-latest", central_dir)
    elif not (central_dir / LOCK_FILENAME).exists():
        (central_dir / LOCK_FILENAME).touch()
        info(f"Locked {release.tag} so cleanup keeps it. Unlock with: {BOLD}ripple --unlock {release.slug}:{release.tag}{R}")

    for parent_dir in symlink_dirs:
        if not parent_dir.is_dir():
            continue

        label = SYMLINK_TARGET_LABELS.get(parent_dir, str(parent_dir))

        if update_latest:
            make_symlink(parent_dir / f"{release.slug}-latest", central_dir, destination_label=label)
        else:
            make_symlink(parent_dir / release.tag, central_dir, destination_label=label)


def link_locked_versions(central_base: Path, symlink_dirs: list[Path]) -> tuple[bool, bool]:
    crate_dir = central_base / "crate"
    if not crate_dir.is_dir():
        return False, False
    has_locked_versions = False
    linked_any = False
    for slug_dir in crate_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        latest_tag = _latest_tag(slug_dir)
        for ver_dir in slug_dir.iterdir():
            if ver_dir.is_dir() and (ver_dir / LOCK_FILENAME).exists():
                has_locked_versions = True
                for parent_dir in symlink_dirs:
                    if not parent_dir.is_dir():
                        continue

                    label = SYMLINK_TARGET_LABELS.get(parent_dir, str(parent_dir))

                    link_path = parent_dir / ver_dir.name
                    if not link_path.is_symlink() or link_path.resolve() != ver_dir.resolve():
                        if not linked_any:
                            info("Linking missing locked versions...")
                            linked_any = True
                        make_symlink(link_path, ver_dir, destination_label=label)

                    # A locked version can also be the latest one; it then needs the alias too.
                    if latest_tag == ver_dir.name:
                        latest_link = parent_dir / f"{slug_dir.name}-latest"
                        if not latest_link.is_symlink() or latest_link.resolve() != ver_dir.resolve():
                            if not linked_any:
                                info("Linking missing locked versions...")
                                linked_any = True
                            make_symlink(latest_link, ver_dir, destination_label=label)
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

        latest_tag = _latest_tag(slug_dir)

        old_dirs: list[Path] = []
        for item in slug_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                if latest_tag and item.name == latest_tag:
                    continue
                if (item / LOCK_FILENAME).exists():
                    info(f"Keeping locked version: {slug_dir.name}/{item.name}")
                    continue
                old_dirs.append(item)

        # Without a .latest-version record nothing marks the current build, so keep
        # the newest by name rather than emptying the source.
        if not latest_tag and old_dirs:
            old_dirs.sort()
            keep = old_dirs.pop()
            info(f"No latest record for {slug_dir.name}, keeping newest: {keep.name}")

        for old_dir in sorted(old_dirs):
            size = _dir_size(old_dir)
            total_freed += size
            info(f"Removing {slug_dir.name}/{old_dir.name} {DIM}({size / 1_048_576:.0f} MiB){R}")
            shutil.rmtree(old_dir, ignore_errors=True)
            removed_count += 1

    # Compare against both spellings: the link records the path as it was written,
    # which differs from the resolved one when the store sits under a symlink.
    store_roots = {cfg.central_base, cfg.central_base.resolve()}
    dangling_count = 0
    for sym_dir in symlink_dirs:
        if not sym_dir.is_dir():
            continue

        for link in sym_dir.iterdir():
            if not link.is_symlink() or link.exists():
                continue
            if not any(is_within(root, _link_target(link)) for root in store_roots):
                continue
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


def list_installed(cfg: Config) -> None:
    step("Installed Versions")
    crate_dir = cfg.central_base / "crate"
    any_found = False
    for slug, api in SOURCES.items():
        store_dir = crate_dir / slug
        if not store_dir.is_dir():
            continue

        latest_tag = _latest_tag(store_dir)
        versions = sorted([p for p in store_dir.iterdir() if p.is_dir() and not p.name.startswith(".")], reverse=True)
        if not versions:
            continue
        any_found = True
        ui.print(f"{C_TL}│{R}  {CYAN}[{slug}]{R}  {BOLD}{api.name}{R}")
        for v in versions:
            markers = []
            if latest_tag and v.name == latest_tag:
                markers.append(GREEN + "latest" + R)
            if (v / LOCK_FILENAME).exists():
                markers.append(YELLOW + "locked" + R)
            tag_str = f"{C_TL}│{R}    " + (CYAN + v.name + R if latest_tag and v.name == latest_tag else v.name)
            if markers:
                tag_str += "  " + DIM + "← " + R + ", ".join(markers)
            ui.print(tag_str)
        ui.print(f"{C_TL}│{R}")
    if not any_found:
        warn("No versions installed yet.")


def parse_spec(spec: str) -> tuple[str, str]:
    slug, sep, tag = spec.partition(":")
    if not sep or not slug or not tag:
        raise RuntimeError(f"Expected SLUG:TAG format, got '{spec}'")
    return slug, tag


def toggle_lock(central_base: Path, spec: str, *, lock: bool) -> None:
    step(f"{'Locking' if lock else 'Unlocking'} Version")
    slug, tag = parse_spec(spec)
    version_dir = central_base / "crate" / slug / tag
    if not version_dir.is_dir():
        raise RuntimeError(f"Version directory not found: {version_dir}")
    lock_file = version_dir / LOCK_FILENAME
    if lock:
        lock_file.touch()
        ok(f"Locked: {DIM}{version_dir}{R}")
    elif lock_file.exists():
        lock_file.unlink()
        ok(f"Unlocked: {DIM}{version_dir}{R}")
    else:
        info(f"Already unlocked: {DIM}{version_dir}{R}")
