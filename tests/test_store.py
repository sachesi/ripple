import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ripple import archive, config, http, sources, store
from ripple.constants import LOCK_FILENAME


class QuietTestCase(unittest.TestCase):
    """Silence the reporting helpers of one module so test output stays readable."""

    module = None
    extra_quiet: tuple = ()

    def setUp(self):
        names = ("step", "info", "ok", "warn") + self.extra_quiet
        self._patches = [patch.object(self.module, n) for n in names if hasattr(self.module, n)]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])


class ConfigTests(unittest.TestCase):
    def test_round_trip(self):
        cfg = config.Config(central_base=Path("/store"), enabled_sources=["ge-proton"], manage_umu=True)
        self.assertEqual(config.Config.from_dict(cfg.to_dict()), cfg)

    def test_config_without_manage_umu_is_still_usable(self):
        # Configs written before manage_umu existed must not be silently discarded.
        cfg = config.Config.from_dict({"central_base": "/store", "enabled_sources": ["ge-proton"]})
        self.assertEqual(cfg.central_base, Path("/store"))
        self.assertEqual(cfg.enabled_sources, ["ge-proton"])
        self.assertFalse(cfg.manage_umu)

    def test_corrupt_config_warns_instead_of_failing_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json")
            with patch.object(config, "CONFIG_PATH", path), patch.object(config, "warn") as warn:
                self.assertIsNone(config.load_config())
            self.assertTrue(warn.called)

    def test_missing_config_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(config, "CONFIG_PATH", Path(tmp) / "absent.json"), patch.object(config, "warn") as warn:
                self.assertIsNone(config.load_config())
            self.assertFalse(warn.called)


class SpecParsingTests(unittest.TestCase):
    def test_valid_spec(self):
        self.assertEqual(store.parse_spec("ge-proton:GE-Proton10-20"), ("ge-proton", "GE-Proton10-20"))

    def test_tag_may_contain_colons(self):
        self.assertEqual(store.parse_spec("umu:1:2"), ("umu", "1:2"))

    def test_rejects_malformed_specs(self):
        for spec in ("ge-proton", "", ":TAG", "ge-proton:"):
            with self.subTest(spec=spec), self.assertRaises(RuntimeError):
                store.parse_spec(spec)


class ExtractionTests(unittest.TestCase):
    def _tar_with_member(self, name):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            payload = b"payload"
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            tf.addfile(member, io.BytesIO(payload))
        buf.seek(0)
        return buf

    def test_member_escaping_the_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dest"
            dest.mkdir()
            with tarfile.open(fileobj=self._tar_with_member("../escaped"), mode="r") as tf:
                with self.assertRaises(RuntimeError):
                    archive.safe_extract(tf, dest)
            self.assertFalse((Path(tmp) / "escaped").exists())

    def test_ordinary_member_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dest"
            dest.mkdir()
            with tarfile.open(fileobj=self._tar_with_member("proton/file"), mode="r") as tf:
                archive.safe_extract(tf, dest)
            self.assertEqual((dest / "proton" / "file").read_bytes(), b"payload")


class CachyosAssetTests(unittest.TestCase):
    def test_suffixes_are_ordered_best_first(self):
        with patch.object(sources, "detect_cpu_level", return_value=3):
            self.assertEqual(sources._cachyos_suffixes(), ["x86_64_v3", "x86_64_v2", "x86_64"])
        with patch.object(sources, "detect_cpu_level", return_value=1):
            self.assertEqual(sources._cachyos_suffixes(), ["x86_64"])

    def test_best_runnable_asset_is_chosen(self):
        matches = [
            "https://example.invalid/proton-x86_64.tar.xz",
            "https://example.invalid/proton-x86_64_v3.tar.xz",
            "https://example.invalid/proton-x86_64_v2.tar.xz",
        ]
        with patch.object(sources, "detect_cpu_level", return_value=3):
            self.assertEqual(sources._cachyos_choose(matches), "https://example.invalid/proton-x86_64_v3.tar.xz")
        with patch.object(sources, "detect_cpu_level", return_value=2):
            self.assertEqual(sources._cachyos_choose(matches), "https://example.invalid/proton-x86_64_v2.tar.xz")

    def test_asset_built_for_a_newer_cpu_is_not_offered(self):
        with patch.object(sources, "detect_cpu_level", return_value=2):
            self.assertFalse(sources._cachyos_asset_filter("https://example.invalid/proton-x86_64_v4.tar.xz"))
            self.assertTrue(sources._cachyos_asset_filter("https://example.invalid/proton-x86_64_v2.tar.xz"))


class CleanupTests(QuietTestCase):
    module = store

    def _store(self, tmp, slug, tags, latest=None):
        slug_dir = Path(tmp) / "crate" / slug
        for tag in tags:
            (slug_dir / tag).mkdir(parents=True)
            (slug_dir / tag / "proton").write_text("x")
        if latest:
            (slug_dir / ".latest-version").write_text(latest + "\n")
        return slug_dir

    def test_latest_and_locked_survive_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = self._store(tmp, "ge-proton", ["v1", "v2", "v3"], latest="v3")
            (slug_dir / "v1" / LOCK_FILENAME).touch()
            cfg = config.Config(central_base=Path(tmp), enabled_sources=["ge-proton"])

            store.remove_old_versions(cfg, [])

            self.assertTrue((slug_dir / "v1").is_dir())
            self.assertFalse((slug_dir / "v2").exists())
            self.assertTrue((slug_dir / "v3").is_dir())

    def test_without_a_latest_record_the_newest_version_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = self._store(tmp, "ge-proton", ["v1", "v2"])
            cfg = config.Config(central_base=Path(tmp), enabled_sources=["ge-proton"])

            store.remove_old_versions(cfg, [])

            self.assertFalse((slug_dir / "v1").exists())
            self.assertTrue((slug_dir / "v2").is_dir())

    def test_only_broken_links_into_our_store_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_path = root / "store"
            (store_path / "crate").mkdir(parents=True)
            targets = root / "compatibilitytools.d"
            targets.mkdir()

            ours = targets / "ge-proton-latest"
            ours.symlink_to(store_path / "crate" / "ge-proton" / "gone")
            theirs = targets / "someone-elses-proton"
            theirs.symlink_to(root / "elsewhere" / "gone")

            cfg = config.Config(central_base=store_path, enabled_sources=[])
            store.remove_old_versions(cfg, [targets])

            self.assertFalse(ours.is_symlink())
            self.assertTrue(theirs.is_symlink())

    def test_links_are_recognised_when_the_store_sits_under_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            (real / "crate").mkdir(parents=True)
            store_path = root / "link-to-store"
            store_path.symlink_to(real)
            targets = root / "compatibilitytools.d"
            targets.mkdir()

            ours = targets / "ge-proton-latest"
            ours.symlink_to(store_path / "crate" / "ge-proton" / "gone")

            cfg = config.Config(central_base=store_path, enabled_sources=[])
            store.remove_old_versions(cfg, [targets])

            self.assertFalse(ours.is_symlink())


class PinnedInstallTests(QuietTestCase):
    module = store
    def test_pinned_install_is_locked_so_cleanup_keeps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "store"
            store_path.mkdir()
            release = sources.ReleaseInfo("GE Proton", "ge-proton", "v9", "https://example.invalid/p-x86_64.tar.gz")

            def fake_extract(archive, dest):
                extracted = Path(dest) / "root"
                extracted.mkdir()
                (extracted / "proton").write_text("x")
                return extracted

            with (
                patch.object(store, "download_file", lambda url, dest, label: Path(dest).write_bytes(b"")),
                patch.object(store, "extract_archive", fake_extract),
            ):
                store.install_release(release, store_path, [], update_latest=False)

            version_dir = store_path / "crate" / "ge-proton" / "v9"
            self.assertTrue(version_dir.is_dir())
            self.assertTrue((version_dir / LOCK_FILENAME).exists())
            self.assertFalse((store_path / "crate" / "ge-proton" / ".latest-version").exists())

            cfg = config.Config(central_base=store_path, enabled_sources=["ge-proton"])
            store.remove_old_versions(cfg, [])
            self.assertTrue(version_dir.is_dir())


class DownloadTests(QuietTestCase):
    module = http
    extra_quiet = ("DownloadProgressBar",)

    class _Response:
        def __init__(self, body, declared_length):
            self._body = body
            self.headers = {"Content-Length": str(declared_length)}

        def read(self, size):
            chunk, self._body = self._body[:size], self._body[size:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_truncated_download_is_rejected_and_cleaned_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "archive.tar.gz"
            with patch.object(http, "_open_url", return_value=self._Response(b"short", 100)):
                with self.assertRaises(RuntimeError):
                    http.download_file("https://example.invalid/a.tar.gz", dest, "test")
            self.assertFalse(dest.exists())

    def test_complete_download_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "archive.tar.gz"
            with patch.object(http, "_open_url", return_value=self._Response(b"complete", 8)):
                http.download_file("https://example.invalid/a.tar.gz", dest, "test")
            self.assertEqual(dest.read_bytes(), b"complete")


class TransportTests(unittest.TestCase):
    def test_plain_http_is_refused(self):
        with self.assertRaises(RuntimeError):
            http._require_https_url("http://example.invalid/a.tar.gz")

    def test_redirect_to_plain_http_is_refused(self):
        handler = http._HTTPSOnlyRedirectHandler()
        with self.assertRaises(RuntimeError):
            handler.redirect_request(None, None, 302, "Found", {}, "http://example.invalid/a.tar.gz")


class SourceRegistryTests(unittest.TestCase):
    def test_every_source_is_reachable_over_https(self):
        for slug, api in sources.SOURCES.items():
            with self.subTest(slug=slug):
                http._require_https_url(api.url)
                self.assertTrue(api.name and api.description)

    def test_unknown_slug_names_the_valid_ones(self):
        with self.assertRaises(RuntimeError) as ctx:
            sources.source_api("no-such-source")
        self.assertIn("ge-proton", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
