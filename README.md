# ripple

CLI tool to manage Proton builds. Downloads releases to a central store and symlinks them into compatibility tool paths for Steam, Bottles, Lutris, and Leyen.

## Features

- Centralized storage for Proton builds.
- Automatic symlinking for Steam (Native/Flatpak), Bottles (Native/Flatpak), Lutris (Native/Flatpak), and Leyen.
- CPU instruction set detection (v2, v3, v4) for build compatibility.
- "latest" and source-specific (e.g. `ge-proton-latest`) symlink aliases.

## Installation

```bash
pip install .
```

To build an RPM:
```bash
make ba-local
```

## Usage

Run the interactive wizard:
```bash
ripple
```

For specific actions:
```bash
ripple --help
```

### Configuration
- Config: `~/.config/ripple/config.json`
- Store: `~/.local/share/ripple/store`

Built with Gemini
