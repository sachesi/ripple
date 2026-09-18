
import tarfile
from pathlib import Path

from .ui import info


def is_within(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    # The "data" filter is the only one that also checks where links point. 3.14
    # uses it by default, older releases need it set, and Pythons without filters
    # rely on the checks below alone.
    if hasattr(tarfile, "data_filter"):
        tf.extraction_filter = tarfile.data_filter
    resolved_dest = dest.resolve()
    for member in tf.getmembers():
        member_target = (dest / member.name).resolve()
        if not is_within(resolved_dest, member_target):
            raise RuntimeError(f"Unsafe archive member path: {member.name}")
        if member.issym() or member.islnk():
            # A symlink points relative to its own folder, a hardlink to the archive
            # root; an absolute linkname replaces the base and fails the check.
            base = (dest / member.name).parent.resolve() if member.issym() else resolved_dest
            if not is_within(resolved_dest, (base / member.linkname).resolve()):
                raise RuntimeError(f"Unsafe archive link: {member.name} -> {member.linkname}")
        elif not (member.isfile() or member.isdir()):
            raise RuntimeError(f"Unsupported archive member type: {member.name}")
        tf.extract(member, path=dest)


def extract_archive(archive: Path, dest: Path) -> Path:
    info(f"Extracting {archive.name} ...")
    with tarfile.open(archive) as tf:
        top_dirs = {Path(m.name).parts[0] for m in tf.getmembers() if m.name}
        safe_extract(tf, dest)

    if len(top_dirs) == 1:
        return dest / top_dirs.pop()
    subdirs = [p for p in dest.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(subdirs) == 1:
        return subdirs[0]
    raise RuntimeError(f"Cannot determine extracted root folder. Found: {[p.name for p in subdirs]}")
