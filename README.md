# Vigil

Vigil is a scheduled maintenance check for Flutter apps you have already shipped. It compares each repo with store and SDK floors you have approved, watches policy sources (Apple news, Play Policy Deadlines, Flutter releases, and more), and verifies major dependency bumps with canary builds so your todo list is **Ready** (safe to bump) or **Blocked** (skip) — not untested noise.

It does not open pull requests and it does not replace Dependabot or Sentry. Your monitored projects, snapshots, holds, and reports live on **your machine** (not in this git repo). Flutter is the supported stack. Linux, macOS, and Windows are supported for paths, tray, notifications, and scan timers. Licensed under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for scope.

## Quick start

Needs **Python 3.11+**. For package checks and canaries, have `flutter` on your `PATH`.

If `vigil` is not on your PATH yet, `python -m vigil …` (or `py -3 -m vigil …` on Windows) works the same.

### 1. Install

**Linux (Fedora):**

```bash
sudo dnf install python3 pipx python3-gobject libappindicator-gtk3 gnome-shell-extension-appindicator
git clone https://github.com/Daddoo-Dev/Vigil.git && cd vigil
./packaging/install.sh
```

**Linux (Debian / Ubuntu):**

```bash
sudo apt install python3 python3-venv python3-gi gir1.2-ayatanaappindicator3-0.1 libnotify-bin
git clone https://github.com/Daddoo-Dev/Vigil.git && cd vigil
./packaging/install.sh
```

If `vigil` is missing after install, add `~/.local/bin` to your `PATH` and open a new terminal.

**Windows:**

1. Install [Python 3.11+](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. Clone `https://github.com/Daddoo-Dev/Vigil.git` (or download the ZIP and unpack it).
3. Double-click `packaging\install.bat`  
   or in PowerShell from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\install.ps1
```

That creates a venv under `%LOCALAPPDATA%\vigil\venv`, puts `vigil` on your **user PATH**, adds Start Menu entries, and registers a scheduled scan task (default monthly). Open a **new** terminal afterward so PATH updates.

To install and jump straight into the wizard:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\install.ps1 -Setup
```

(`.ps1` is the real installer; `.bat` is only a double-click wrapper. PowerShell is the usual scripting host on modern Windows.)

**macOS** (no App Store build; local unsigned install):

1. Install Python 3.11+ ([python.org](https://www.python.org/downloads/) or `brew install python`).
2. Clone `https://github.com/Daddoo-Dev/Vigil.git` (or download the ZIP).
3. Double-click `packaging/install.command`  
   or in Terminal:

```bash
git clone https://github.com/Daddoo-Dev/Vigil.git && cd vigil
chmod +x packaging/install.command packaging/install-macos.sh
./packaging/install-macos.sh
# or jump into the wizard:
./packaging/install-macos.sh --setup
```

That creates a venv under `~/Library/Application Support/vigil/venv`, adds `vigil` to your shell PATH (`~/.zprofile` / `~/.bash_profile`), installs **Vigil** / **Vigil Setup** / **Vigil Tray** under `~/Applications`, and registers LaunchAgents for a scheduled scan and tray at login.

The first time macOS may block an unsigned app: **right-click → Open**, or System Settings → Privacy & Security → **Open Anyway**. That is expected without App Store / notarization.

### 2. First-run wizard

```bash
vigil setup
```

Or just `vigil` when nothing is configured yet. That will:

1. Create your config directories and example files  
2. Install desktop hooks (Linux apps/timer, Windows Start Menu/PATH/task, or macOS Applications/LaunchAgents)  
3. Let you pick the folder that holds your Flutter apps, then check which ones to monitor  
4. Offer to run the first scan and open the report  

**Scans canary majors on purpose.** Vigil tries each *new* resolvable major (debug APK, pubspec restored afterward) so the report lists **verified bumps** and **blocked upgrades**, not raw “major behind” noise. A canary failure on one app (for example `file_picker` major 13) is stored as a **global** block so that major is hidden across your other apps. Solver conflicts can be per-app. **Smart recheck:** Ready/Blocked stay put while that package’s pub latest is unchanged; Vigil re-canaries only when that latest moves, or when a recorded conflicting dependency (`blocked_by`) moves. A busy store/SDK proposal list or a `degraded` banner is still normal on day one — use `vigil review` for those.

### 3. Day to day

Typical monthly loop: run `vigil scan` → act on **Ready** dependency bumps and floor findings (Flutter pin, target API, iOS) → bump versions → commit → CI/store. Later scans skip unchanged verdicts and only retest when something relevant moved.

| Goal | Command |
| --- | --- |
| See last result | `vigil` or `vigil status` |
| Open the report | `vigil open` (also Start Menu → **Vigil** on Windows) |
| Scan again | `vigil scan` (slow; verifies majors fleet-wide) |
| Accept / dismiss store & SDK proposals | `vigil review` |
| Change which apps are monitored | `vigil projects` |
| Automatic scan schedule | `vigil schedule` (`weekly` / `biweekly` / `monthly` / `off` / `days 45`) |
| Reinstall desktop hooks + timer | `vigil desktop` |
| Status icon | `vigil tray` |

On Linux search the apps grid for **Vigil**. On Windows use Start Menu → **Vigil**. On macOS open **Vigil** from `~/Applications`.

## Where files live

| What | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Config | `~/.config/vigil/` | `~/Library/Application Support/vigil/` | `%APPDATA%\vigil\` |
| State | `~/.local/state/vigil/` | `~/Library/Caches/vigil/` | `%LOCALAPPDATA%\vigil\` |
| Reports | `~/.local/share/vigil/reports/` | `~/Library/Application Support/vigil/reports/` | `%LOCALAPPDATA%\vigil\reports\` |

Useful config files (examples ship under `src/vigil/examples/`):

| File | Role |
| --- | --- |
| `repos.yaml` | Monitored apps |
| `requirements.yaml` | Hand-approved floors (only `vigil review` edits) |
| `requirements.pending.yaml` | Proposals from sources |
| `sources.yaml` | Policy/news feeds (includes Play Policy Deadlines) |
| `holds.yaml` | Ready / Blocked package verdicts (Vigil writes these) |
| `settings.yaml` | Notify, schedule, `probe_builds` / `probe_budget` |
| `expiries.yaml` | Certs / accounts you track by hand |

## What Vigil checks

**Floors (per app)**  
Flutter / Dart pins and constraints (actionable “set FVM or pubspec to X” when unpinned), Android `targetSdk` / `compileSdk`, iOS deployment target, and hand-approved Xcode / Play API requirements.

**Sources (proposals only until review)**  
Apple Developer News and upcoming requirements, Android Developers Blog, **Google Play Policy Deadlines** (stable table Google updates in place), Play target API pages, Flutter/Dart release feeds. Fetches never write `requirements.yaml`. Policy table rows keep deadlines with the text; review can prefill suggested deadlines.

**Packages**  
`flutter pub outdated` and pub.dev (discontinued / replaced / advisories). Resolvable majors are canaried to **Ready** or **Blocked**. Only Ready majors appear as bump recommendations; Blocked stays in the report’s blocked section. Unchanged Ready/Blocked majors are not re-canaried until that package’s latest (or a recorded `blocked_by` companion) moves. Signing/setup canary failures are treated as inconclusive, not global blocks.

**Schedule**  
Default monthly timer via `vigil desktop` / installers. Change with `vigil schedule` or `settings.yaml` (`weekly`, `biweekly`, `monthly`, `off`, or `days` + `every_days`). Timers use local time; if the machine was asleep/off, Linux `Persistent=true` (and the host equivalents) catch up when they can.

| Setting | When it runs |
| --- | --- |
| `monthly` (default) | **1st of each month** — Linux 00:00; macOS / Windows 09:00 |
| `weekly` | **Mondays** — Linux 00:00; macOS / Windows 09:00 |
| `biweekly` | Every **14 days** after the timer last fired (also ~15 minutes after boot on Linux the first time) |
| `days` + `every_days: N` | Every **N days** on the same interval pattern as biweekly |
| `off` | No automatic scan — run `vigil scan` yourself |

**Other**  
Expiry dates you list in `expiries.yaml`. Desktop notify after a non-ok scan when enabled.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests do not touch the network.
