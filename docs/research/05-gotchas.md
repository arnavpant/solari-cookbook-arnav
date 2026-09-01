# Gotchas

Things that cost an afternoon if you meet them cold. This is the source for the
README's gotchas section and for the launch post.

**Every entry says how it was established.** "Verified here" means we hit it against the
real API or the real app and have the output. "Solari docs" means we are repeating their
documentation and have not independently confirmed it. That distinction is the whole
value of the list, so do not blur it.

---

## 1. GnuCash cannot open ANY SQLite book without `libdbd-sqlite3`

**Verified here.** The most expensive one by far.

GnuCash reaches SQL backends through libdbi, whose SQLite driver ships as a *separate*
package. Install `gnucash` alone and every book fails to open with:

> No suitable backend was found for /root/book.gnucash.

which reads exactly like a corrupt file and is not. Evidence:

```
libdbd-sqlite3 installed? 0
libdbi drivers present: <none>
   ...after apt-get install libdbd-sqlite3...
libdbi drivers now: libdbdsqlite3.la
                    libdbdsqlite3.so
```

Fix: `apt-get install -y gnucash libdbd-sqlite3`.

## 2. `pkg.install` does not run `apt-get update`, and fails without raising

**Verified here.** A fresh Solari desktop has *empty* apt package lists, so the first
install of anything fails:

```
pkg.install('apt', ['gnucash'])
-> PkgInstallResult(exitCode=100, stderr='E: Unable to locate package gnucash\n')
```

Two traps in one. First, this is not a missing repository - the image is Ubuntu 22.04
with `main`, `restricted`, `universe`, `multiverse` and the `-updates`/`-security`
pockets already in `sources.list`. `apt-cache policy` simply listed no package files at
all. One `apt-get update` (6 seconds) fixes it.

Second, **it returned a failure object instead of raising.** Code that only catches
exceptions sails straight past a failed install.

## 3. `revert()` does not work on desktops, and `fromSnapshot` does not exist

**Verified here.** `snapshot()` succeeds and hands back an id in about 14 seconds.
Nothing in the Python SDK can then consume it:

| Attempt | Result |
|---|---|
| `revert(snap)` immediately | `GatewayError: Not revertable` |
| `revert(snap)` after a 25s settle | `GatewayError: Not revertable` |
| `pause(session)` then `revert(snap)` | `GatewayError: Not found` |
| `create(fromSnapshot=...)` and three other spellings | `TypeError` - not a parameter |

The docs describe `fromSnapshot` for making "independent, ready-to-use copies of a
prepared machine." It is absent from `solari-desktop==0.2.0`. Plan for software-level
reset instead.

## 4. An empty CA store breaks only `connect()`, nothing else

**Verified here.** Some Pythons (MSYS2/mingw, minimal Linux images) ship an OpenSSL CA
store with zero certificates. Every HTTP call still works, because `httpx` bundles
certifi - so creating a desktop succeeds and returns a session id. Then the WebSocket
control channel, which uses `websockets` and the stdlib default context, dies:

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
unable to get local issuer certificate
```

The asymmetry is what makes it confusing: the API clearly works, and only `connect()`
fails. Check with `len(ssl.create_default_context().get_ca_certs())` - ours was `0`.

Fix, before any SSL context is created:

```python
import certifi, os
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
```

That took us from 0 CAs to 118.

## 5. There are two different `connect()` methods

**Verified here.** `client.connect(session_id)` re-attaches to an existing desktop and
returns the handle, but does **not** open the control channel. The next call fails with:

```
ConnectionError: Not connected - call connect() first
```

You need both: `d = await client.connect(sid)` then `await d.connect()`.

## 6. `SyncDesktopClient` is only half synchronous

**Verified here**, and the SDK says so itself:

> the returned Desktop handle is async, so prefer DesktopClient when driving the
> control channel

It wraps the *client* calls (`create`, `get`, `destroy`, `pause`, `resume`, `connect`)
on a private event loop. Everything you actually drive a desktop with - `screenshot`,
`mouse.*`, `keyboard.*`, `fs.*`, `exec`, `snapshot`, `revert` - is still a coroutine.
Own one loop and wrap it yourself.

## 7. The default template auto-starts Chrome over the screen

**Verified here.** A fresh desktop opens Google Chrome on `about:blank`, occupying most
of the viewport. For a computer-use benchmark that is a contaminant: it changes what the
agent sees and invites it to interact with the wrong window. `pkill -f chrome`.

## 8. GnuCash's Tip Of The Day is not where you would look for it

**Verified here.** It opens on every launch and steals focus. Writing
`~/.config/gnucash/gnucash.conf` does nothing - GnuCash 4.x uses GSettings/dconf.

The obvious key name is wrong too:

```
gsettings set org.gnucash.GnuCash.general show-tip-of-the-day false
-> No such key 'show-tip-of-the-day'
```

The real location, found by listing the schema on a live desktop:

```
schema  org.gnucash.GnuCash.dialogs.totd
key     show-at-startup
```

And `export $(dbus-launch)` does **not** work - `dbus-launch` emits semicolon-separated
statements that the export mangles. Use `dbus-run-session --`:

```
dbus-run-session -- gsettings set org.gnucash.GnuCash.dialogs.totd show-at-startup false
```

## 9. GnuCash's SQLite backend really does commit on every edit

**Verified here**, and this one is load-bearing rather than annoying - the whole grading
design depends on it.

Created an account through the GUI, pressed **no** Save, then read the book:

```
before: accounts(12): Assets, Checking, Consulting, ... Water
after:  accounts(13): Assets, Checking, Consulting, ... Software Subscriptions, ... Water
```

If GnuCash behaved like its XML backend, every task would partly have been a test of
whether the agent remembered to save.

Bonus: an open book has a row in its `gnclock` table. That is a reliable programmatic
test of "did GnuCash actually open this file" - see gotcha 10 for why you need one.

## 10. Checking that the file still parses proves nothing

**Verified here, the embarrassing way.** Our first automated verification reported PASS
because the book still contained 12 transactions after GnuCash "opened" it. It did -
precisely because GnuCash had refused to open it and never touched the file. A book that
was never opened parses perfectly.

Two lessons, both now baked into the scripts: assert on a *positive* signal of the thing
you care about (a `gnclock` row), and look at the screenshot.

## 11. `process.list()` returns processes with no names

**Verified here.** You cannot find a process by name through the SDK. Every entry comes
back blank:

```
process.list() -> list, len 75
first item: ProcessInfo(pid=1, name='', cmd=None)
entries matching 'gnucash': 0
```

Meanwhile, on the same machine at the same moment:

```
$ pgrep -a gnucash
6353 gnucash /root/book.gnucash
```

`ProcessInfo` has exactly the fields you would want - `pid`, `name`, `cmd` - and
populates only `pid`. This cost us a 123-second readiness timeout on a desktop where
the app had already been running for two minutes. Use `exec("pgrep -x <name>")`.

## 12. `pkill -f <name>` will kill your own shell

**Verified here.** `-f` matches against the *full command line*, and the command line
you are running usually mentions the thing you are killing:

```sh
sh -c "pkill -f gnucash; rm -f /root/book.gnucash*"
#              ^^^^^^^                 ^^^^^^^ the shell matches its own pattern
```

The shell kills itself, `exec` returns `exitCode -1`, and every command after the
`pkill` silently never runs. Worse, it can look like it worked: our reset appeared fine
because the next step overwrote the book anyway.

Use `pkill -x <name>`, which matches the process *name* exactly - your shell is `sh`,
so it cannot match itself.

## 13. `mouse.scroll()` cannot express a direction

**Verified here.** The signature is:

```python
async def scroll(self, x: int, y: int, *, button: Optional[MouseButton] = None,
                 humanize: Optional[bool] = None) -> None
```

No direction. No amount. And direction cannot be smuggled through `button`, because:

```python
MouseButton = Literal["left", "right", "middle"]
_BUTTON_CODES = {"left": 1, "middle": 2, "right": 3}
```

X11 encodes wheel-up and wheel-down as buttons 4 and 5, and neither is reachable - the
type does not admit them and `_button_to_code` would raise. So "scroll up" is
unrepresentable through the typed API.

cubicle's workaround: move the pointer to the target, then send `Page_Up` / `Page_Down`,
which GnuCash's register honours. Agents keep working directional scrolling; it just
travels over the keyboard.

## 14. `mouse.drag()` takes two dicts, not four coordinates

**Verified here.** Not `drag(x, y, to_x, to_y)`, which is the obvious guess and what we
originally wrote:

```python
async def drag(self, frm: Dict[str, int], to: Dict[str, int],
               button: MouseButton = "left") -> None
```

Call it as `drag({"x": 1, "y": 2}, {"x": 8, "y": 9})`.

Related, and documented in the SDK's own source: named buttons are converted to X11
integer codes before going on the wire, because "without this the wire carries a raw
string and the guest's JSON decode fails with `cannot unmarshal string into ... button
of type int`". Worth knowing if you ever hand-roll the HTTP call.

---

## Repeated from Solari's own docs, not independently verified

Listed for completeness, and labelled honestly.

- **`429 ConcurrencyLimitExceeded` is never retryable.** A slot frees only when *you*
  pause or kill a session. We designed around this but never actually hit the cap.
- **`GET /sessions/:id` always returns 404.** Use `health()` instead.
- **Never parse the error prose** - only the HTTP status or `code` is stable.
- **Retry policies differ by client**: the VM client retries any `5xx` or
  `retryable: true` up to 6 attempts; the browser client retries only 502/503/504 up to 2.
- **A paused VM does not count against the running-VM limit.**
- **`exec` returning 200 only means the HTTP call succeeded**; the command's result is in
  `exitCode`. (Gotcha 2 is the same failure through `pkg.install`, which we did hit.)

---

## Application gotchas (GnuCash, not Solari)

### 15. The register's date field silently truncates a four-digit year

**Verified here, and the grader is what caught it.**

Typing `03/14/2026` into the register's date cell stores **`2020-03-14`**. On screen the
cell reads `03/14/20`, which next to neighbours like `04/18/26` looks like ordinary
two-digit-year formatting rather than a six-year error.

```
typed:  03/14/2026
stored: 2020-03-14 10:59:00
```

Type `03/14/26` instead.

This is the single best argument in the project for grading against the database. The
screen looked right. An LLM-judge scoring the screenshot would have passed it. The SQL
assertion on `post_date` failed it immediately, with the exact reason.

### 16. GnuCash opens at ~800x700 and cuts off the amount column

**Verified here.** On a 1280x720 desktop the window opens roughly 803px wide, which puts
the register's **Withdrawal** and **Balance** columns off the right edge. An agent that
cannot see the amount column is being measured on the wrong thing, so cubicle maximizes
the window as part of starting every task.

Worth knowing: GnuCash positions its dialogs relative to the screen rather than centring
them on the parent window, so maximizing does **not** move dialog coordinates. Oracles
recorded before and after maximization stay valid.
