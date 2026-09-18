# Contributing

Bugs and ideas go to the [issue tracker](https://github.com/sachesi/ripple/issues); security
problems do not, see [SECURITY.md](SECURITY.md).

Before a change goes in:

- The tests pass. CI runs them on every supported Python for every push and pull request.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `fix:`, `feat:`, `docs:` and so on, with a subject that says what changed for someone
  using Ripple.
- A new option goes into `build_parser` and into the three completions under
  `packaging/usr/share/`, which are written by hand.
- Behaviour described in `docs/` changes with the code that implements it.

## Where things are

    src/ripple/cli.py        options, the update run, and finding the launcher folders,
                             including the Flatpak access check
    src/ripple/config.py     the config file and the wizard
    src/ripple/constants.py  paths, the launcher folders, CPU level detection
    src/ripple/sources.py    the Proton sources and which asset of a release fits this
                             machine
    src/ripple/store.py      installing into the store, links, locks, cleanup, listing
    src/ripple/umu.py        umu-run in ~/.local/bin
    src/ripple/http.py       HTTPS-only requests, retries, paging, downloads
    src/ripple/archive.py    tar extraction that stays inside its destination
    src/ripple/ui.py         terminal output, prompts, the progress bar
    src/ripple/_version.py   the version, read by pyproject.toml

A new source is an entry in `SOURCES` in `sources.py`: the releases API, a filter for
the asset and, if a release carries builds for several CPU levels, a function that picks
one. Forgejo and Gitea instances answer the same way GitHub does, but have no
`/releases/latest`, which `has_latest_endpoint=False` accounts for.

## Running

    PYTHONPATH=src python -m ripple --help
    PYTHONPATH=src python -m unittest discover -s tests

The tests use temporary folders and patch the network away; they touch neither your
store nor your launchers.

## Releasing

The version lives in `src/ripple/_version.py` and in `flake.nix`; both change in the
`release:` commit, and the tag is `v` followed by the version.
