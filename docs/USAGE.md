# ripple usage

## Interactive wizard
Run `ripple` without arguments to start the configuration and installation wizard.

## Command line options
Running `ripple` with no options updates every enabled source and, if enabled,
umu-run.

- `--configure`: Re-run the configuration wizard to change the store path,
  enabled sources, and umu management.
- `--list`: Show installed versions in the central store, and the managed
  umu-run build when umu management is enabled.
- `--list-remote <slug>`: List upstream releases for a source. Accepts any
  Proton slug (`ge-proton`, `dw-proton`, `cachyos-proton`, `em-proton`) or
  `umu`. Long lists are paged.
- `--download <slug>:<tag>`: Download and install a specific version. The
  version is locked automatically so that `--remove-old` keeps it.
- `--lock <slug>:<tag>`: Prevent a version from being removed during cleanup.
- `--unlock <slug>:<tag>`: Remove a lock so cleanup can reclaim the version.
- `--remove-old`: Delete every stored version except the latest and the locked
  ones, then remove symlinks into the store that no longer resolve.

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
