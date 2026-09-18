# Security

Please report a vulnerability privately rather than in a public issue: through
[a private advisory](https://github.com/sachesi/ripple/security/advisories/new) on GitHub,
or by mail to sachesi <xsachesi@pm.me>. Say what you found, how to reproduce it and which
version you ran; a fix is worked out with you before anything is published.

Only the latest release gets fixes.

## What counts

Ripple downloads archives from upstream projects and unpacks them into your home folder.
The parts where a mistake matters most:

- Extraction: an archive member that lands outside its destination, through `..`, an
  absolute path or a link, is a vulnerability.
- Transport: every request is HTTPS, redirects included. A way to make Ripple fetch over
  plain HTTP is a vulnerability.
- Links and cleanup: `--remove-old` and relinking delete and replace things. Anything that
  can lead them to remove or overwrite a path outside the store and the launcher folders
  it links into is a vulnerability.
- Flatpak access: Ripple grants read-only access to the store and nothing else, and only
  after asking.

Ripple does not verify the builds themselves beyond their size; it trusts the release
pages of the projects it follows. A compromised upstream release is a matter for that
project.
