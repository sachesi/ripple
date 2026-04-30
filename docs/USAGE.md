# ripple usage

## Interactive wizard
Run `ripple` without arguments to start the configuration and installation wizard.

## Command line options
- `--list`: Show installed versions in the central store.
- `--install <slug>`: Download and install the latest version for a source (e.g. `ge-proton`).
- `--lock <version>`: Prevent a version from being removed during cleanup.

## Symlinks
Installed versions are stored in `~/.local/share/ripple/store/crate`. 

The tool symlinks tools into:
- Steam: `~/.local/share/Steam/compatibilitytools.d/`
- Lutris: `~/.local/share/lutris/runners/wine/`
- Bottles: `~/.local/share/bottles/data/bottles/runners/`

### Aliases
The tool maintains symlink aliases in the destination directories:
- `<slug>-latest`: points to the latest version for that specific source.
