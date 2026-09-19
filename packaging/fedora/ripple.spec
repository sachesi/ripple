%define _debugsource_template %{nil}
%define debug_package %{nil}

Name:           ripple
# The release workflow and Copr set Version to the tag they build.
Version:        3.2.0
Release:        1%{?dist}
Summary:        Download and install Proton releases with centralized storage
License:        GPL-3.0-or-later
URL:            https://github.com/sachesi/ripple
Source0:        %{url}/archive/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
BuildRequires:  python-rpm-macros

%description
ripple is a CLI tool to download and install Proton builds into one
central store, then symlink them into Steam, Bottles, and Lutris paths.

%prep
%setup -q -n %{name}-%{version}

# pyproject.toml references shell completion files under assets/ that
# don't exist upstream yet; strip data-files so pip wheel can build.
sed -i '/^\[tool.setuptools.data-files\]/,/^\[/ {
  /^\[tool.setuptools.data-files\]/d
  /^"/d
}' pyproject.toml

%build
python3 -m pip wheel --no-build-isolation --no-deps -w dist .

%install
python3 -m pip install --no-deps --ignore-installed --no-warn-script-location \
    --root %{buildroot} --prefix %{_prefix} dist/ripple-*.whl

%check
test -x %{buildroot}%{_bindir}/%{name}

%files
%license LICENSE
%doc README.md
%{_bindir}/%{name}
%{python3_sitelib}/%{name}/
%{python3_sitelib}/%{name}-*.dist-info/

%changelog
