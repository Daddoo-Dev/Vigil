# Vigil

Vigil is a monthly maintenance check for Flutter apps you have already shipped. It compares each repo with store and SDK requirements you have approved, and it files news snippets for you to accept or dismiss. It does not open pull requests and it does not replace Dependabot or Sentry.

Your monitored projects, snapshots, and reports live on **your machine** (not in this git repo). Flutter is the supported stack. Linux, macOS, and Windows are supported for paths, tray, and notifications. Licensed under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for scope.

## Quick start

Needs **Python 3.11+**. For package checks, have `flutter` on your `PATH`.

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

That creates a venv under `%LOCALAPPDATA%\vigil\venv`, puts `vigil` on your **user PATH**, adds Start Menu entries, and registers a monthly scan task. Open a **new** terminal afterward so PATH updates.

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

That creates a venv under `~/Library/Application Support/vigil/venv`, adds `vigil` to your shell PATH (`~/.zprofile` / `~/.bash_profile`), installs **Vigil** / **Vigil Setup** / **Vigil Tray** under `~/Applications`, and registers LaunchAgents for a monthly scan and tray at login.

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

The first scan can take several minutes. A busy proposal list or a `degraded` banner is normal on day one — use `vigil review` later for proposals that affect your apps.

### 3. Day to day

| Goal | Command |
| --- | --- |
| See last result | `vigil` or `vigil status` |
| Open the report | `vigil open` (also Start Menu → **Vigil** on Windows) |
| Scan again | `vigil scan` |
| Accept / dismiss proposals | `vigil review` |
| Change which apps are monitored | `vigil projects` |
| Status icon | `vigil tray` |

On Linux search the apps grid for **Vigil**. On Windows use Start Menu → **Vigil**. On macOS open **Vigil** from `~/Applications`.

## Where files live

| What | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Config | `~/.config/vigil/` | `~/Library/Application Support/vigil/` | `%APPDATA%\vigil\` |
| State | `~/.local/state/vigil/` | `~/Library/Caches/vigil/` | `%LOCALAPPDATA%\vigil\` |
| Reports | `~/.local/share/vigil/reports/` | `~/Library/Application Support/vigil/reports/` | `%LOCALAPPDATA%\vigil\reports\` |

## What Vigil checks

- Flutter / Dart pins and constraints, Android `targetSdk` / `compileSdk`, iOS deployment target  
- `flutter pub outdated` and pub.dev (discontinued / replaced packages)  
- Requirement pages you configure; proposals never edit `requirements.yaml` until `vigil review`  
- Expiry dates you list in `expiries.yaml`  

Examples live under `src/vigil/examples/`. Contribution notes: [CONTRIBUTING.md](CONTRIBUTING.md).

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests do not touch the network.
