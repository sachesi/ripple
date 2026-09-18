# Using Ripple

## Running and configuring

`ripple` with no options updates every enabled source and, if it is turned on,
`umu-run`. On the first run, or when the config cannot be read, it starts the
configuration wizard before doing anything else; `ripple --configure` runs it again to
change the store, the sources or umu management.

The config is `~/.config/ripple/config.json` and the store defaults to
`~/.local/share/ripple/store`.

## Options

    --list                  installed versions, with the latest and the locked ones marked,
                            and the managed umu-run if there is one
    --list-remote SLUG      upstream releases usable on this machine, paged
    --download SLUG:TAG     install one version and lock it
    --lock SLUG:TAG         keep a version through --remove-old
    --unlock SLUG:TAG       let --remove-old take it again
    --remove-old            delete everything but the latest and the locked versions, then
                            the links into the store that no longer resolve
    --configure             run the wizard again

The slugs are `ge-proton`, `dw-proton`, `cachyos-proton` and `em-proton`; `umu` is
accepted by `--list-remote` and `--download` as well. A tag is the release name upstream
gives it, as `--list-remote` prints it.

GitHub allows 60 API requests an hour without a token. Ripple asks for the latest
release first and pages through the rest only as far as it has to, but listing the whole
history of a source several times in a row can run into the limit; the error says when it
resets.

## The store

Each build is unpacked once into `crate/<slug>/<tag>` under the store. `--remove-old`
keeps the version recorded as the latest of each source and every locked one; if that
record is missing it keeps the newest by name. A locked version is marked by a `.locked`
file in its folder.

## Where the links go

- Steam: `compatibilitytools.d/` under `~/.steam/root/` or `~/.steam/steam/`, whichever
  exists, otherwise `~/.local/share/Steam/compatibilitytools.d/`
- Bottles: `~/.local/share/bottles/runners/`
- Lutris: `~/.local/share/lutris/runners/wine/`
- Leyen: `~/.local/share/leyen/proton/`

`~/.local/share` is `$XDG_DATA_HOME` when that is set. A launcher gets links only when it
is installed, and its folder is created if it is not there yet.

Flatpak installs of the same launchers get theirs under `~/.var/app/<app-id>/data/`. The
sandbox of a Flatpak usually cannot follow a link out to the store, so Ripple checks, and
if it cannot read it asks whether to grant that application read-only access with
`flatpak override --user --filesystem=<store>:ro`. Run without a terminal, it skips that
launcher and prints the command instead.

Every launcher gets `<slug>-latest`, which is moved to the new build on each update, and
a link under its own tag for every locked version. Where a real folder sits in the place
of a link, Ripple asks before replacing it, and leaves it alone when there is no terminal
to ask on.
