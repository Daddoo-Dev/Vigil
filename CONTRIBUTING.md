# Contributing to Vigil

## First-run path

End users should only need:

```bash
./packaging/install.sh                 # Linux
# Windows: packaging\install.bat  or  packaging\install.ps1
# macOS:   packaging/install.command  or  packaging/install-macos.sh
vigil setup                            # or bare `vigil` when unset
```

`vigil.setup.run_setup` owns that wizard. Host desktop hooks: `vigil.windows_desktop`, `vigil.macos_desktop`, Linux code in `vigil.desktop`. No App Store / notarized Mac builds in v1. Keep README Quick start aligned with the install scripts.

## Scope

Vigil is a **personal maintenance watchdog for published Flutter apps**.

In scope for this repository:

- Scan Flutter projects (pubspec, Android Gradle, iOS deployment target, pub outdated, pub.dev).
- Fetch requirement sources, propose changes, and apply them only through `vigil review`.
- Write a self-contained HTML report and a small desktop tray / notification layer.
- Run on **Linux, macOS, and Windows** for paths, tray (pystray), and notify backends.

Out of scope for v1 (and not required for a useful open repo):

- Opening pull requests or editing app source trees.
- Replacing Dependabot, Sentry, or CI.
- Shipping scanner packs for other major frameworks yet (React Native, native Android-only, and so on). Flutter is the **reference scanner pack**; other frameworks can plug into the same report and requirements pipeline later.
- Committing anyone’s real `repos.yaml`, snapshots, or reports. Those stay in per-user directories outside the git tree.

## Personal data stays off git

| What | Where |
| --- | --- |
| Your config | host config dir (`~/.config/vigil` on Linux, Application Support on macOS, `%APPDATA%\vigil` on Windows) |
| Snapshots / status / log | host state dir |
| HTML reports | host data dir under `vigil/reports` |

Only the empty examples under `src/vigil/examples/` are tracked. Never add a filled-in `repos.yaml` from your machine.

## Layout tips

- **Paths:** `vigil.host.default_path_roots` and `Paths.from_env`. Override with `VIGIL_CONFIG_DIR`, `VIGIL_STATE_DIR`, `VIGIL_REPORTS_DIR`.
- **Notify:** `vigil.notify.get_notifier()` — Linux `notify-send`, macOS `osascript`, Windows toast.
- **Tray:** `vigil.tray.get_tray()` — pystray today; `TrayBackend` is the swap point.
- **Scanners:** `vigil.scanners.*` — Flutter pack is the reference. New frameworks should mirror that shape and feed `scan.py` / the report context.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests must not hit the network. Prefer injecting `notify_fn`, `outdated_runner`, and path env vars over calling real desktop APIs.
