import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ripple import cli


class TargetDiscoveryTests(unittest.TestCase):
    def test_flatpak_ids_come_from_flatpak(self):
        result = cli.subprocess.CompletedProcess([], 0, "com.valvesoftware.Steam\nnet.lutris.Lutris\n", "")
        with (
            patch.object(cli.shutil, "which", return_value="/usr/bin/flatpak"),
            patch.object(cli.subprocess, "run", return_value=result) as run,
        ):
            app_ids = cli._installed_flatpak_ids()

        self.assertEqual(app_ids, {"com.valvesoftware.Steam", "net.lutris.Lutris"})
        run.assert_called_once_with(
            ["flatpak", "list", "--app", "--columns=application"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_only_installed_apps_get_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            native = root / "native"
            flatpak = root / "flatpak"
            with (
                patch.object(cli, "NATIVE_TARGET_DIRS", {"steam": (native,), "lutris": (root / "lutris",)}),
                patch.object(cli, "FLATPAK_TARGET_DIRS", {"com.valvesoftware.Steam": flatpak}),
                patch.object(cli.shutil, "which", side_effect=lambda command: "/usr/bin/steam" if command == "steam" else None),
                patch.object(cli, "_installed_flatpak_ids", return_value={"com.valvesoftware.Steam"}),
                patch.object(cli, "_flatpak_can_read", return_value=True),
            ):
                targets = cli.prepare_symlink_dirs(root / "store")

            self.assertEqual(targets, [native, flatpak])
            self.assertTrue(native.is_dir())
            self.assertTrue(flatpak.is_dir())
            self.assertFalse((root / "lutris").exists())

    def test_inaccessible_flatpak_is_skipped_without_a_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "steam-flatpak"
            with (
                patch.object(cli, "NATIVE_TARGET_DIRS", {}),
                patch.object(cli, "FLATPAK_TARGET_DIRS", {"com.valvesoftware.Steam": target}),
                patch.object(cli, "_installed_flatpak_ids", return_value={"com.valvesoftware.Steam"}),
                patch.object(cli, "_flatpak_can_read", return_value=False),
                patch.object(cli, "_grant_flatpak_access", return_value=False),
            ):
                targets = cli.prepare_symlink_dirs(root / "store")

            self.assertEqual(targets, [])
            self.assertTrue(target.is_dir())

    def test_native_steam_prefers_an_existing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "missing" / "compatibilitytools.d"
            second = root / "Steam" / "compatibilitytools.d"
            second.parent.mkdir()

            self.assertEqual(cli._native_target((first, second)), second)

    def test_flatpak_override_is_narrow_and_verified(self):
        app_id = "com.valvesoftware.Steam"
        store = Path("/tmp/ripple test/store")
        with (
            patch.object(cli.sys.stdin, "isatty", return_value=True),
            patch.object(cli, "yn", return_value=True),
            patch.object(cli, "_flatpak_can_read", return_value=True),
            patch.object(cli, "info"),
            patch.object(cli.subprocess, "run") as run,
        ):
            granted = cli._grant_flatpak_access(app_id, store)

        self.assertTrue(granted)
        run.assert_called_once_with(
            ["flatpak", "override", "--user", f"--filesystem={store}:ro", app_id],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
