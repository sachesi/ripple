
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
    # Pin the filter so extraction behaves the same on every supported Python;
    # 3.12+ picks one itself and the default changed in 3.14.
    if hasattr(tarfile, "tar_filter"):
        tf.extraction_filter = tarfile.tar_filter
    resolved_dest = dest.resolve()
    for member in tf.getmembers():
        member_target = (dest / member.name).resolve()
        if not is_within(resolved_dest, member_target):
            raise RuntimeError(f"Unsafe archive member path: {member.name}")
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
