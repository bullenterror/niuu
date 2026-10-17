# CPython 3.14.8 security backports

These build inputs backport two published fixes without changing the Python
interpreter, ABI, reported version, or installed application dependencies.
Remove each patch after a stable upstream runtime includes its fix; a different
base version or module checksum deliberately fails the build until reviewed.

| CVE | Upstream commit | Runtime file |
| --- | --- | --- |
| CVE-2025-15367 | [b234a2b](https://github.com/python/cpython/commit/b234a2b67539f787e191d2ef19a7cbdce32874e7) | `poplib.py` |
| CVE-2026-87910 | [fb2f0bb](https://github.com/python/cpython/commit/fb2f0bbc3b35264f09cc2cb2934b7987527a6bc2) and [d9565e5](https://github.com/python/cpython/commit/d9565e54b1fc6d63c5be9afd58114499128fa57b) (test correction) | `tarfile.py` |

CPython 3.14.8 ships the earlier backports for CVE-2026-17084 (`stringprep.py`),
CVE-2026-15806 (`urllib/request.py`), CVE-2026-15310 (`zipfile/__init__.py`) and
CVE-2026-19672 (`tarfile.py`), so they were removed. `verify.py` keeps their
exploit regressions as guards on the runtime.

The POP3 fix is deliberately taken from the newer upstream line: it rejects
C0/DEL characters in commands, including credentials. Older Python branches
have not adopted that behavior because it can reject previously accepted
inputs. Niuu has no direct POP3 integration; bundled Python now enforces that
security boundary for callers too.

`build.py` verifies the upstream 3.14.8 source archive and all three complete,
unmodified upstream patches against `manifest.json`, applies them with no
fuzz, runs CPython's two affected test suites, and exports only two modules.
The build tools and source tree do not enter the final images.

`install.py` checks every original and replacement module before writing any
file, copies those two modules into the interpreter's actual stdlib directory,
and removes their obsolete bytecode caches. This covers both `/usr/local`
Python and OpenShell's managed Python. `verify.py` checks installed hashes and
runs exploit regressions for the two backported CVEs and the four fixed upstream.

## Scanner evidence

Version-based scanners still recognize the real Python 3.14.8 version.
The container scan therefore resolves an immutable image digest and runs the
same verifier inside that image with networking disabled and a read-only
filesystem. A failed hash or regression check stops scanning before any fixed
statement can be issued.

Only after verification, `vex.py` creates OpenVEX `fixed` statements for these
two CVEs and the exact Python package/runtime path in that same image digest.
It rejects unrelated image scans, module hashes, versions and interpreter
locations. Syft catalogs each image once (`scan.sh`); both Grype passes match
that SBOM, with Syft and Grype pinned by checksum in `install-scanners.sh`.
Every scan retains the Syft SBOM, the raw Grype JSON, runtime hash/test evidence,
VEX document and filtered Grype JSON as CI artifacts for 30 days. The filtered
JSON retains the original findings in `ignoredMatches` with the VEX reason;
SARIF reports the remaining actionable findings. No global ignore rule or
version spoofing is used.

The upstream patches and derived modules are covered by `LICENSE.cpython`.

## Runtime boundary

These backports cover Python in the four shipped images. The SSH VM restore
script uses Python installed on the remote VM; that separate operating-system
runtime is not modified by these image builds and must receive its own vendor
security updates. No remote host was patched as part of this remediation.
