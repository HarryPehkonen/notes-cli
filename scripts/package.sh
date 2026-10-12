#!/usr/bin/env sh
# Package notes-cli from a clean tree: noarch deb + rpm, reproducible from source.
#
#   scripts/package.sh            build both into dist/
#   scripts/package.sh deb        build only the deb
#   scripts/package.sh rpm        build only the rpm
#
# The deb is built with dpkg-deb from a control file generated below (single
# binary, Depends: python3). The rpm is built with rpmbuild from a generated
# spec. Both stages assert their contents: a package stage that silently ships
# the wrong files is not a gate.
set -eu
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' notes)
[ -n "$VERSION" ] || { echo "cannot read VERSION from notes"; exit 1; }
MAINTAINER="Harri Pehkonen <harry.pehkonen@gmail.com>"
SUMMARY="command-line client for a Notes server"
DESCRIPTION="Read, search, edit, create, tag and archive notes from the shell
against any Notes-compatible server. Python standard library only - no
dependencies."
mkdir -p dist

build_deb() {
  root=dist/.debroot/notes-cli-$VERSION
  rm -rf dist/.debroot
  mkdir -p "$root/DEBIAN" "$root/usr/bin" "$root/usr/share/man/man1" "$root/usr/share/doc/notes-cli"
  install -m 755 notes "$root/usr/bin/notes"
  scdoc < man/notes.1.scd > "$root/usr/share/man/man1/notes.1"
  gzip -9n "$root/usr/share/man/man1/notes.1"
  install -m 644 LICENSE "$root/usr/share/doc/notes-cli/copyright"
  cat > "$root/DEBIAN/control" <<EOF
Package: notes-cli
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9)
Maintainer: $MAINTAINER
Description: $SUMMARY
 .
$(printf '%s\n' "$DESCRIPTION" | sed 's/^/ /')
EOF
  deb=dist/notes-cli_${VERSION}_all.deb
  dpkg-deb --root-owner-group --build "$root" "$deb" >/dev/null
  rm -rf dist/.debroot

  # Assert contents: exactly the binary, the man page, the copyright file.
  c=$(dpkg-deb -c "$deb" | grep -cE ' \./usr/bin/notes$| \./usr/share/man/man1/notes\.1\.gz$| \./usr/share/doc/notes-cli/copyright$')
  [ "$c" -eq 3 ] || { echo "DEB CONTENTS WRONG (expected 3 file entries, got $c)"; exit 1; }
  i=$(dpkg-deb -I "$deb" | grep -cE 'Package: notes-cli$|Architecture: all$|Depends: python3 \(>= 3\.9\)$|Section: utils$')
  [ "$i" -eq 4 ] || { echo "DEB CONTROL WRONG (expected 4 fields, got $i)"; exit 1; }
  echo "built $deb"
}

build_rpm() {
  tree=dist/.rpmbuild
  rm -rf "$tree"
  for d in BUILD RPMS SOURCES SPECS; do mkdir -p "$tree/$d"; done
  tar -czf "$tree/SOURCES/notes-cli-$VERSION.tar.gz" --transform "s,^,notes-cli-$VERSION/," notes man/notes.1.scd LICENSE
  cat > "$tree/SPECS/notes-cli.spec" <<EOF
Name:           notes-cli
Version:        $VERSION
Release:        1
Summary:        $SUMMARY
License:        Unlicense
URL:            https://github.com/HarryPehkonen/notes-cli
BuildArch:      noarch
Requires:       python3 >= 3.9
Source0:        notes-cli-$VERSION.tar.gz

%description
$DESCRIPTION

%prep
%setup -q

%build

%install
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_mandir}/man1 %{buildroot}%{_datadir}/doc/%{name}
install -m 755 notes %{buildroot}%{_bindir}/notes
scdoc < man/notes.1.scd > %{buildroot}%{_mandir}/man1/notes.1
gzip -9n %{buildroot}%{_mandir}/man1/notes.1
install -m 644 LICENSE %{buildroot}%{_datadir}/doc/%{name}/copyright

%files
%{_bindir}/notes
%{_mandir}/man1/notes.1*
%{_datadir}/doc/%{name}/copyright

%changelog
* Mon Oct 12 2026 $MAINTAINER - $VERSION-1
- first packaged version
EOF
  rpmbuild --define "_topdir $(pwd)/$tree" -bb "$tree/SPECS/notes-cli.spec" >/dev/null
  mv "$tree"/RPMS/noarch/notes-cli-*.rpm dist/
  rpm=dist/notes-cli-$VERSION-1.noarch.rpm

  # Assert contents: exactly the binary, the man page, the copyright file.
  c=$(rpm -qlp "$rpm" | grep -cE '/usr/bin/notes$|/usr/share/man/man1/notes\.1|/usr/share/doc/notes-cli/copyright$')
  [ "$c" -eq 3 ] || { echo "RPM CONTENTS WRONG (expected 3 file entries, got $c)"; exit 1; }
  rm -rf "$tree"
  echo "built $rpm"
}

case "${1:-all}" in
  deb) build_deb ;;
  rpm) build_rpm ;;
  all) build_deb; build_rpm ;;
  *) echo "usage: scripts/package.sh [deb|rpm|all]"; exit 2 ;;
esac
