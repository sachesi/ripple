# Ripple

Ripple downloads Proton builds and keeps one copy of each in a central store, then links
them into the compatibility tool folders of Steam, Bottles, Lutris and Leyen, native or
Flatpak. A build that three launchers use takes the disk space of one.

It follows GE Proton, DW Proton, CachyOS Proton and EM Proton, and can keep `umu-run` up
to date in `~/.local/bin`. For CachyOS Proton it picks the x86-64-v2, v3 or v4 build your
CPU runs best.

## Installing

    pip install .

or with Nix:

    nix run github:sachesi/ripple

On NixOS, add `inputs.ripple.packages.${pkgs.system}.default` to
`environment.systemPackages`. Python 3.10 or later, no dependencies outside the standard
library. Shell completions for bash, zsh and fish are installed with the package.

## Using it

The first run asks where the store goes, which sources to follow and whether to manage
`umu-run`, then installs the newest build of each. Every run after that updates them:

    ripple

Each launcher sees `<source>-latest`, for example `ge-proton-latest`, which moves to the
new build on update, so a game set to it never needs touching. A build you want to keep
is locked and linked under its own name:

    ripple --download ge-proton:GE-Proton10-20
    ripple --remove-old        # everything but the latest and the locked ones

Only launchers that are installed get links. A Flatpak launcher that cannot see the
store is offered read-only access to it through `flatpak override --user`; nothing is
granted without asking.

The options, the paths and what happens to links are in [docs/usage.md](docs/usage.md).
Changes go through [CONTRIBUTING.md](CONTRIBUTING.md), and vulnerabilities are reported
as described in [SECURITY.md](SECURITY.md).

GPL-3.0-or-later.
