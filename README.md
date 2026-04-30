# ripple

CLI tool to manage Proton builds. Downloads releases to a central store and symlinks them into compatibility tool paths for Steam, Bottles, Lutris, and Leyen.

## Features

- Centralized storage for Proton builds.
- Automatic symlinking for Steam (Native/Flatpak), Bottles (Native/Flatpak), Lutris (Native/Flatpak), and Leyen.
- CPU instruction set detection (v2, v3, v4) for build compatibility.
- Source-specific symlink aliases such as `ge-proton-latest`.

## Installation

```bash
pip install .
```

To build an RPM:
```bash
make ba-local
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
