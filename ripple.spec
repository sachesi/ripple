%define _debugsource_template %{nil}
%define debug_package %{nil}

Name:           ripple
Version:        3.0.8
Release:        1%{?dist}
Summary:        Download and install Proton releases with centralized storage
License:        GPL-3.0-or-later
URL:            https://github.com/sachesi/ripple
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros

%description
ripple is a CLI tool to download and install Proton builds into one
central store, then symlink them into Steam, Bottles, and Lutris paths.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files ripple

install -Dm644 assets/usr/share/bash-completion/completions/%{name} \
    %{buildroot}%{_datadir}/bash-completion/completions/%{name}
install -Dm644 assets/usr/share/zsh/site-functions/_%{name} \
    %{buildroot}%{_datadir}/zsh/site-functions/_%{name}
install -Dm644 assets/usr/share/fish/vendor_completions.d/%{name}.fish \
    %{buildroot}%{_datadir}/fish/vendor_completions.d/%{name}.fish

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/%{name}
%{_datadir}/bash-completion/completions/%{name}
%{_datadir}/zsh/site-functions/_%{name}
%{_datadir}/fish/vendor_completions.d/%{name}.fish

%changelog
* Mon May 04 2026 sachesi <xsachesi@pm.me> - 3.0.8-1
- Remove all backward compatibility logic
- Use dynamic User-Agent with correct version
- Simplify config and archive extraction logic
- Bump version to 3.0.8

* Mon May 04 2026 sachesi <xsachesi@pm.me> - 3.0.7-1
- Remove global 'latest' symlink, keep only slug-specific aliases
- Add automatic cleanup of legacy global 'latest' links
- Bump version to 3.0.7

* Mon May 04 2026 sachesi <xsachesi@pm.me> - 3.0.6-1
- Swap version file for .real_version when linking as latest
- Refine symlink relinking and alias management
- Bump version to 3.0.6

* Thu Apr 30 2026 sachesi <xsachesi@pm.me> - 3.0.5-1
- Add latest and slug-latest symlinks to destination paths
- Update README and add docs/USAGE.md
- Add Nix flake and direnv support

* Mon Apr 27 2026 sachesi <xsachesi@pm.me> - 3.0.3-1
- pyproject.toml - fix license
- bump version to 3.0.3

* Mon Apr 27 2026 sachesi <xsachesi@pm.me> - 3.0.2-2
- Consolidate build logic into root Makefile
- Add missing BuildRequires: python3-pip for %%pyproject_wheel in COPR

* Fri Apr 24 2026 sachesi <xsachesi@pm.me> - 3.0.2-1
- Refactor CLI into src/ripple modules split by logic
- Keep tar extraction safety checks and tighten versioned User-Agent
- Bump package metadata to 3.0.2

* Fri Apr 24 2026 sachesi <xsachesi@pm.me> - 3.0.1-3
- Fix fish completion path to use vendor_completions.d
- Add Makefile for local workflow

* Thu Apr 23 2026 sachesi <xsachesi@pm.me> - 3.0.1-1
- Bump version to 3.0.1

* Thu Apr 23 2026 sachesi <xsachesi@pm.me> - 3.0.0-2
- Include /usr/bin/ripple in %%files to fix unpackaged file error
- Switch pyproject license to SPDX string and drop deprecated classifier
- Fix License

* Thu Apr 23 2026 sachesi <xsachesi@pm.me> - 3.0.0-1
- Add Fedora RPM spec and COPR SRPM workflow
- Install shell completions from assets/usr/share
