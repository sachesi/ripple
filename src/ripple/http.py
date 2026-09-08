
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ._version import __version__
from .constants import TIMEOUT
from .ui import DownloadProgressBar


def _require_https_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"Refusing non-HTTPS URL: {url}")


class _HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects that would downgrade the transport to plain HTTP."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        _require_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HTTPSOnlyRedirectHandler)


def _open_url(url: str) -> Any:
    _require_https_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": f"ripple/{__version__}"})
    return _opener.open(req, timeout=TIMEOUT)  # nosec B310


def fetch_json(url: str, *, attempts: int = 3) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with _open_url(url) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError(_rate_limit_message(url, e)) from e
            if e.code >= 500 and attempt < attempts:
                last_exc = e
                time.sleep(min(2 ** (attempt - 1), 4))
                continue
            raise RuntimeError(f"Server returned error {e.code} for {url}") from e
        except urllib.error.URLError as e:
            if attempt < attempts:
                last_exc = e
                time.sleep(min(2 ** (attempt - 1), 4))
                continue
            raise RuntimeError(f"Network error after {attempts} attempts for {url}: {e.reason}") from e
    raise RuntimeError(f"Request failed for {url}: {last_exc}")


def _rate_limit_message(url: str, e: urllib.error.HTTPError) -> str:
    reset = e.headers.get("x-ratelimit-reset")
    when = ""
    if reset and reset.isdigit():
        when = f", resets at {time.strftime('%H:%M %Z', time.localtime(int(reset)))}"
    return f"GitHub API rate limit exceeded (403){when} for {url}"


def iter_releases(url: str, *, per_page: int = 100) -> Iterator[Any]:
    """Yield releases page by page so callers can stop before paging the whole history.

    GitHub allows 60 unauthenticated requests per hour, and popular sources have
    hundreds of releases, so callers looking for one tag must not fetch them all.
    """
    page = 1
    sep = "&" if "?" in url else "?"
    while True:
        batch = fetch_json(f"{url}{sep}per_page={per_page}&page={page}")
        if not batch:
            return
        yield from batch
        if len(batch) < per_page:
            return
        page += 1


def download_file(url: str, dest: Path, label: str) -> None:
    try:
        with _open_url(url) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            pb = DownloadProgressBar(label)
            chunks = 0
            while data := resp.read(1 << 17):
                out.write(data)
                downloaded += len(data)
                chunks += 1
                pb.update(downloaded, total, chunks)
            if total and downloaded != total:
                raise RuntimeError(f"Truncated download for {label}: got {downloaded} of {total} bytes.")
            pb.done()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
