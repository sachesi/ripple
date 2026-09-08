# ripple

CLI tool to manage Proton builds. Downloads releases to a central store and symlinks them into compatibility tool paths for Steam, Bottles, Lutris, and Leyen.

## Features

- Centralized storage for Proton builds.
- Installed-app detection and automatic target-directory creation for Steam, Bottles, Lutris, and Leyen (Native/Flatpak).
- Narrow read-only store access setup when a Flatpak sandbox cannot follow Ripple's central-store symlinks.
- CPU instruction set detection (v2, v3, v4) for build compatibility.
- Source-specific symlink aliases such as `ge-proton-latest`.

## Installation

```bash
pip install .
```

### Nix

Run directly:
```bash
nix run github:sachesi/ripple
```

Install to system (NixOS):
Add `inputs.ripple.packages.${pkgs.system}.default` to `environment.systemPackages`, or expose it through your own flake outputs.


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
