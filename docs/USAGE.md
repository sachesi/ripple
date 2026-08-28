# ripple usage

## Interactive wizard
Run `ripple` without arguments to start the configuration and installation wizard.

## Command line options
- `--list`: Show installed versions in the central store.
- `--download <slug>:<tag>`: Download and install a specific version.
- `--lock <slug>:<tag>`: Prevent a version from being removed during cleanup.

## Symlinks
Installed versions are stored in `~/.local/share/ripple/store/crate`. 

The tool symlinks tools into:
- Steam: `compatibilitytools.d/` under an existing `~/.steam/root/` or
  `~/.steam/steam/`, falling back to
  `~/.local/share/Steam/compatibilitytools.d/`
- Lutris: `~/.local/share/lutris/runners/wine/`
- Bottles: `~/.local/share/bottles/runners/`
- Leyen: `~/.local/share/leyen/proton/`

Ripple also detects Flatpak installations and uses each application's directory
under `~/.var/app/`. If a sandbox cannot read the central store, Ripple asks
before granting that application read-only access with a per-user Flatpak
override. In non-interactive runs, the inaccessible target is skipped and the
required command is printed instead.

### Aliases
The tool maintains symlink aliases in the destination directories:
- `<slug>-latest`: points to the latest version for that specific source.
