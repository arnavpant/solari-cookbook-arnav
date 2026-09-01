# Solari API — verified notes

Ground truth for `cubicle`. Sources: introspection of `solari-desktop==0.2.0` /
`solari-core==0.2.0` installed from PyPI, the nine cookbook examples, and
docs.getsolari.com. Anything not verified is marked.

Docs use flat paths: `docs.getsolari.com/{quickstart,languages,mcp,sessions,browser-api,
profiles,recording,stealth,proxies,captcha,desktops,sandboxes,templates,snapshots,
volumes,regions,organizations,pricing,errors}`.

## Packages

```
solari-desktop   0.2.0   DesktopClient, SyncDesktopClient, TemplateClient, VolumeClient
solari-sandbox   0.2.0   SandboxClient
solari-core      0.2.0   Desktop, Sandbox and the sub-namespaces
```

Base URL `https://api.getsolari.com`. The standalone `DesktopClient`/`SandboxClient`
require `base_url` explicitly; only the TS umbrella `SolariClient` defaults it.

**Everything is `async` except `SyncDesktopClient` / `SyncTemplateClient` /
`SyncVolumeClient`.** For a harness, use the sync clients.

## DesktopClient

```python
create(*, template="default", ttl_seconds=None, resolution=None, cpu=None,
       mem_mb=None, metadata=None, record=None, timeout_ms=None,
       lifecycle=None, volumes=None) -> Desktop
connect(session_id) -> Desktop
attach(session) -> Desktop
get(session_id) -> GetDesktopResponse
pause(session_id) -> DesktopLifecycleResponse
resume(session_id) -> Desktop
destroy(session_id) -> DeleteDesktopResponse
aclose() -> None
```

Note there is **no `fromSnapshot` parameter** in the 0.2.0 Python `create()` signature,
even though the snapshots doc describes one. Do not design around forking.

## Desktop

```
snapshot(name=None) -> str          # returns snapshot id; machine keeps running
revert(snapshot_id) -> None         # restores THIS machine, same session id
exec(cmd, *, args, cwd, timeout_ms, stream) -> ExecResult
exec_stream(cmd, on_chunk, ...) -> ExecResult
open(name, args=None) -> int        # pid; fails if binary absent from image
screenshot(*, format="png", quality=None) -> bytes
health() -> HealthResult            # .ready
metrics() -> MetricsResult
run_code(code, *, language, context_id, on_stdout, on_stderr) -> RunCodeResult
create_code_context(language="python") -> str
env(vars) -> None
set_timeout(timeout_ms) -> dict
preview_url(port) -> dict
upload_url(path=None) / download_url(path) -> dict     # signed URLs
pause() / resume() / close() / kill() / reconnect() / connect()
```

### Sub-namespaces on Desktop

```
d.fs         read(path)->bytes, read_text, write(path,data,mode), list, stat,
             remove(path,recursive), mkdir
d.mouse      move(x,y,humanize=), click(...), double_click(x,y,button=),
             down(x,y,button), up(x,y,button), scroll(...), drag(...)
d.keyboard   type(text), press(keys), hotkey(*keys), down(keys), up(keys)
d.screen     set(w,h), size(), cursor()
d.clipboard  get(), set(text)          # EXCLUDED from cubicle's action space
d.process    list(), kill(pid), start(...), signal(pid, signal=)
d.ports      list()
d.pkg        install(manager, packages) -> PkgInstallResult
```

`d.fs` means no signed-URL dance is needed for file transfer.
`d.pkg.install("apt", ["gnucash"])` is a one-call install.

## Lifecycle semantics

- `close()` drops only the local control channel. The VM keeps running.
- `kill()` / `client.destroy(session_id)` end the session.
- `pause()` parks the machine and saves state.
- **A paused VM does not count against the plan's running-VM limit; resuming counts
  again.** This is the lever for managing a 2-slot cap.
- Idle timeout defaults to **30 minutes**, configurable, and can be set to either pause
  or terminate on expiry via `lifecycle`.
- `timeout_ms` is a **rolling idle window**, not a hard deadline. It resets on every use.

## Snapshots vs pause

- **Snapshot** = a named checkpoint taken while the machine keeps running. Reusable.
- **Pause** = park this machine and resume it later; not a checkpoint.
- Both VMs and sandboxes support snapshots identically.
- `SnapshotView` fields: `id, parent, name, sizeBytes, createdAt, kind, template`.
- Snapshots are per-machine, so N worker desktops need N snapshots.

## Templates

`TemplateClient.build(image, *, name, kind, cpu, mem_mb, timeout_ms=900000, ...)`
builds a custom image. `CompiledImage` fields: `kind, packages, fragment, steps,
localFiles, base, fromTemplate`. Build timeout defaults to 15 minutes.

Not used in cubicle v1 — snapshot/revert is fewer unknowns — but this is how you would
publish a preinstalled GnuCash template later.

## The `default` desktop template

Ships **mousepad, thunar, Chrome, VS Code, LibreOffice**. GnuCash is **not** included.
`open()` fails if the binary is absent; check with `exec("command", args=["-v", name])`.

VM specs are configurable at create: CPU 1-16 cores, memory 2-64 GB, plus resolution.
VMs launch in roughly one second. Every VM exposes a `streamUrl` for live VNC viewing.

## Errors and retries

Every error is JSON: `error` (prose, **not stable — never parse it**), `code`
(machine-readable), `detail`/`message`, and `retryable` (bool, VM gateway only).
**Branch on HTTP status or `code`.**

Exception classes exported: `SolariError, AuthError, ActionError, ConnectionError,
TimeoutError, GatewayError, PlanError, NoCapacityError, ConcurrencyLimitError`.

| Condition | Handling |
|---|---|
| `502`, `503`, `504`, transport errors | Retryable — upstream unreachable or brief capacity gap |
| **`429 ConcurrencyLimitExceeded`** | **NEVER retryable.** A slot frees only when *you* pause or kill a session |
| VM client default policy | Retries any `5xx` or `retryable: true`, up to 6 attempts |
| Browser client default policy | Retries only `502/503/504`, up to 2 attempts |

### Documented traps

1. `GET /sessions/:id` **always returns 404.** Never poll session status that way.
2. A `200` from `exec` means only that the HTTP call succeeded. The command result is in
   `exitCode`. Always check it.
3. TypeScript only: you must `await solari.close()`. The browser client keeps a loopback
   proxy open and the script hangs forever otherwise.
4. Recording is **per session, not per account**. Pass `recording: true` at create or the
   replay endpoint 404s forever. Upload is async after release — poll ~30s.
5. Sandbox commands are **not shell-interpreted**. `run("ls -la")` looks for a binary
   literally named `ls -la`. Put argv in `args`, or run `sh -c` explicitly.

## Pricing

Unified credit balance across browsers, sandboxes, VMs, proxies and captcha.

| Plan | Price | Credit | Max session | Concurrent desktops/sandboxes |
|---|---|---|---|---|
| Free | $0 | $3 | 1 hour | — |
| Starter | $20/mo | $20 | 5 hours | **2** |
| Professional | $200/mo | $200 | — | — |
| Enterprise | custom | — | unlimited | — |

- Browsers billed hourly while active: $0.15/hr (Free) down to $0.05/hr (Enterprise).
  Concurrent browsers 3 to 150+.
- **Sandboxes and VMs billed by size** (vCPUs and memory). VM live screen adds
  **$0.02/hr**.
- Reference point given in the docs: "$20 on Starter buys 200 browser-hours, or about
  350 hours on a small (1 vCPU / 2 GB) sandbox."
- Monthly plan credits do not roll over; separately purchased credits do not expire.

**Implication for cubicle:** a full run is ~2 desktop-hours on the smallest machine.
Cost is effectively free. The binding constraints are the 2-slot concurrency cap and
wall-clock, not money.
