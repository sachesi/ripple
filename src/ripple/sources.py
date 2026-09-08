
import concurrent.futures
import platform
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import detect_cpu_level
from .http import fetch_json, iter_releases
from .ui import C_TL, CYAN, DIM, R, info, paginate_interactive, step, warn


@dataclass
class ReleaseInfo:
    name: str
    slug: str
    tag: str
    asset_url: str


@dataclass(frozen=True)
class SourceAPI:
    name: str
    description: str
    url: str
    pick_asset: Callable[[str], bool]
    choose: Callable[[list[str]], str] | None = None
    has_latest_endpoint: bool = True


def _release_info(slug: str, api: SourceAPI, rel: dict[str, Any]) -> ReleaseInfo | None:
    """Build a ReleaseInfo for this machine, or None when the release has no usable asset."""
    matches = [a["browser_download_url"] for a in rel.get("assets", []) if api.pick_asset(a["browser_download_url"])]
    if not matches:
        return None
    asset_url = api.choose(matches) if api.choose else matches[0]
    return ReleaseInfo(api.name, slug, rel["tag_name"], asset_url)


def _machine_arch() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)


_ARCHIVE_SUFFIX_RE = r"\.(tar\.xz|tar\.gz)$"


def _is_archive(url: str) -> bool:
    return url.endswith((".tar.xz", ".tar.gz"))


def _ge_asset_filter(url: str) -> bool:
    """Accept the GE Proton archive matching this machine's architecture.

    Recent releases ship per-arch assets (e.g. GE-Proton11-5-x86_64.tar.gz,
    GE-Proton11-5-aarch64.tar.gz); older releases shipped a single unsuffixed
    .tar.gz. Reject archives built for a different architecture.
    """
    name = url.rsplit("/", 1)[-1]
    if not _is_archive(name):
        return False
    if f"-{_machine_arch()}.tar." in name:
        return True
    return not re.search(r"-(aarch64|x86_64|arm64)\.tar\.", name)


def _cachyos_suffixes() -> list[str]:
    """Asset suffixes this CPU can run, best first."""
    return [f"x86_64_v{level}" for level in range(detect_cpu_level(), 1, -1)] + ["x86_64"]


def _cachyos_asset_filter(url: str) -> bool:
    return any(re.search(rf"-{re.escape(sfx)}{_ARCHIVE_SUFFIX_RE}", url) for sfx in _cachyos_suffixes())


def _cachyos_choose(matches: list[str]) -> str:
    for sfx in _cachyos_suffixes():
        for url in matches:
            if re.search(rf"-{re.escape(sfx)}{_ARCHIVE_SUFFIX_RE}", url):
                return url
    return matches[0]


SOURCES: dict[str, SourceAPI] = {
    "ge-proton": SourceAPI(
        name="GE Proton",
        description="GloriousEggroll/proton-ge-custom, GitHub",
        url="https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
        pick_asset=_ge_asset_filter,
    ),
    "dw-proton": SourceAPI(
        name="DW Proton",
        description="dawn-winery/dwproton, dawn.wine",
        url="https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases",
        pick_asset=_is_archive,
        # dawn.wine is a Forgejo instance without a /latest shortcut.
        has_latest_endpoint=False,
    ),
    "cachyos-proton": SourceAPI(
        name="CachyOS Proton",
        description="CachyOS/proton-cachyos, GitHub — auto-selects the v2/v3/v4 build",
        url="https://api.github.com/repos/CachyOS/proton-cachyos/releases",
        pick_asset=_cachyos_asset_filter,
        choose=_cachyos_choose,
    ),
    "em-proton": SourceAPI(
        name="EM Proton",
        description="Etaash-mathamsetty/Proton, GitHub",
        url="https://api.github.com/repos/Etaash-mathamsetty/Proton/releases",
        pick_asset=_is_archive,
    ),
}


def source_api(slug: str) -> SourceAPI:
    try:
        return SOURCES[slug]
    except KeyError:
        raise RuntimeError(f"Unknown slug '{slug}'. Valid slugs: {', '.join(SOURCES)}") from None


def fetch_release(slug: str) -> ReleaseInfo:
    """Resolve the newest release with an asset usable on this machine.

    Tries the cheap /releases/latest endpoint first (single object, one API call,
    excludes pre-releases); falls back to walking the /releases list when the
    latest endpoint is missing or has no matching asset.
    """
    api = source_api(slug)
    if api.has_latest_endpoint:
        try:
            release = _release_info(slug, api, fetch_json(f"{api.url}/latest"))
            if release is not None:
                return release
        except RuntimeError:
            pass
    for rel in fetch_json(api.url):
        release = _release_info(slug, api, rel)
        if release is not None:
            return release
    raise RuntimeError(f"No {api.name} release with a matching asset found.")


def fetch_releases_concurrently(slugs: list[str]) -> dict[str, Any]:
    step("Checking for updates")
    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(slugs))) as executor:
        futs = {executor.submit(fetch_release, s): s for s in slugs if s in SOURCES}
        for fut in concurrent.futures.as_completed(futs):
            slug = futs[fut]
            try:
                results[slug] = fut.result()
            except Exception as e:
                results[slug] = e
    return results


def fetch_specific_release(slug: str, tag: str) -> ReleaseInfo:
    step(f"Fetching specific release: {slug} {tag}")
    api = source_api(slug)
    for rel in iter_releases(api.url):
        if rel["tag_name"] != tag:
            continue
        release = _release_info(slug, api, rel)
        if release is None:
            raise RuntimeError(f"Release '{tag}' found but no matching asset for this CPU.")
        info(f"Found {CYAN}{tag}{R}")
        return release
    raise RuntimeError(f"Release tag '{tag}' not found for slug '{slug}'.")


def list_remote_releases(slug: str) -> None:
    step(f"Remote Releases for {slug}")
    api = source_api(slug)
    if api.choose is not None:
        info(f"CPU x86-64-v{detect_cpu_level()} - showing best asset per release")
    items = []
    for rel in iter_releases(api.url):
        release = _release_info(slug, api, rel)
        if release is not None:
            items.append([
                f"{C_TL}│{R}  {CYAN}{release.tag}{R}",
                f"{C_TL}│{R}    {DIM}{Path(release.asset_url).name}{R}"
            ])
    if not items:
        warn("No matching assets found.")
        return
    paginate_interactive(items)
