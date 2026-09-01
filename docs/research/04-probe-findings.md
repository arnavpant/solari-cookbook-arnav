# Probe findings

Task 1 of the plan. Two live probes against the real Solari API on 2026-09-01.
Everything here is an observed result, not a doc claim.

## Summary

| Question | Answer |
|---|---|
| Does GnuCash install from apt? | **Yes — but only after `apt-get update`.** `pkg.install` does not update first |
| Does `revert()` work on a desktop? | **No.** `GatewayError: Not revertable`, under every variation tried |
| Can you create a desktop from a snapshot? | **No.** `fromSnapshot` is not a parameter of `create()` in the Python SDK |
| What does `create(lifecycle=...)` accept? | Not determined — the probe died before Q3 |

Two of the three core assumptions in the design were wrong. The architecture changed
as a result; see "Consequences" below.

## Environment gotcha: empty CA store

The first probe never reached the API. `d.connect()` died with:

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
unable to get local issuer certificate
```

Cause: this machine's Python (MSYS2/UCRT64) ships an OpenSSL CA store with **zero**
certificates (`len(ssl.create_default_context().get_ca_certs()) == 0`). Every HTTP call
still worked, because `httpx` bundles `certifi` — but Solari's WebSocket control channel
uses the `websockets` library and the stdlib default context, so `connect()` alone failed.

Fix, applied at the top of every entrypoint before any SSL context exists:

```python
import certifi, os
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
```

This took the context from 0 to 118 CAs. Worth carrying in the README: the failure is
confusing because creating a desktop succeeds and only `connect()` breaks.

## Q1 — GnuCash installs, after `apt-get update`

First attempt:

```
pkg.install('apt', ['gnucash'])
-> PkgInstallResult(exitCode=100, stderr='E: Unable to locate package gnucash\n')
```

Note it **returned a failure result rather than raising.** Code that only catches
exceptions will sail straight past this. This is the spec's "a 200 only means the HTTP
call worked" gotcha, in its real form.

The cause is not a missing repository. The base image is:

```
PRETTY_NAME="Ubuntu 22.04.5 LTS"
```

and `/etc/apt/sources.list` already contains `main`, `restricted`, `universe`,
`multiverse`, plus `-updates`, `-security` and `-backports`. The problem is that
`apt-cache policy` listed **no package files at all** — only `/var/lib/dpkg/status`.
The package lists were simply never downloaded. `pkg.install` does not run
`apt-get update` for you.

After a manual `apt-get update`:

```
apt-cache search gnucash
-> gnucash - personal and small-business financial-accounting software
   gnucash-common - common files for the financial-accounting software Gnucash
   gnucash-docs - Documentation for gnucash, a personal finance tracking program
```

**Rule: always `apt-get update` before installing anything on a fresh desktop.**

## Q2 — revert() does not work on desktops

`snapshot()` works fine and returns an id quickly:

```
snapshot: snap_dl447c94psyl     (~14s)
snapshot: snap_dl448udahsce     (~14s)
```

Consuming it fails under every variation tried:

| Attempt | Result |
|---|---|
| `revert(snap)` immediately after snapshotting | `GatewayError: Not revertable` |
| `revert(snap)` after a 25s settle wait | `GatewayError: Not revertable` |
| `pause(session)` then `revert(snap)` | `GatewayError: Not found` |
| `create(fromSnapshot=snap)` | `TypeError` — not a parameter |
| `create(from_snapshot=...)`, `create(snapshot=...)`, `create(snapshotId=...)` | `TypeError` — not a parameter |

The docs describe a `fromSnapshot` create parameter for "independent, ready-to-use
copies of a prepared machine." **It does not exist in `solari-desktop==0.2.0`.** So a
desktop snapshot can be taken but not used, at least from Python.

Whether "Not revertable" is a desktop-vs-sandbox restriction, a plan restriction, or a
bug was not worth more credit to determine.

## Q3 — lifecycle shape

Not determined. The first probe died at Q2 before reaching it, and the second probe was
scoped to Q1/Q2. Since the architecture no longer keeps a long-lived desktop parked
between runs, the pause-on-idle setting stopped mattering. **Omit `lifecycle` entirely.**

## Consequences for the design

Snapshot-based per-task isolation is out. The replacement is the software-level reset
already listed as the mitigation in spec §13:

```
setup, once per run:
    create desktop
    apt-get update
    apt-get install -y gnucash          # a few minutes, once

per task:
    pkill gnucash
    rm -rf ~/.config/gnucash ~/.local/share/gnucash   # wipe recent files, geometry, prefs
    rm -f /root/book.gnucash
    fs.write(BOOK_PATH, task.seed())
    open gnucash
```

Wiping GnuCash's config directories matters as much as replacing the book: without it,
recent-file lists, window geometry and saved preferences leak between tasks and a later
task could start from a different UI state than an earlier one.

This is honest and defensible, and the README should describe the reset as
software-level rather than claim snapshot isolation the platform did not give us.

**Stretch, not v1:** `TemplateClient.build(CompiledImage(packages=["gnucash"], ...))`
would bake GnuCash into a custom template so every task could start from a pristine
one-second machine. That is the architecturally correct answer and it would make the
benchmark trivially reproducible. It is unproven, the build timeout is 15 minutes, and
it is not worth spending a 2-day budget on.

## Other observations

The default template's installed GUI apps:

```
libreoffice /usr/bin/libreoffice    soffice /usr/bin/soffice    localc /usr/bin/localc
mousepad    /usr/bin/mousepad       thunar  /usr/bin/thunar     code   /usr/bin/code
google-chrome /usr/bin/google-chrome
```

No `gnumeric`, no `sqlitebrowser`, no `xterm`, no `lobase`. Desktop environment is XFCE
with `x11vnc`. Useful to know: if GnuCash had been unavailable, LibreOffice Calc was the
only realistic fallback host, and it would have been much harder to grade.

`piecash 1.2.1` creates a valid book locally: 25 tables, `Gnucash` schema version
3000000. Ubuntu 22.04 ships GnuCash 4.x, which should upgrade a 3.x book on open — still
to be confirmed live in Task 3 Step 5.
