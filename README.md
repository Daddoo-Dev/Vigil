# Vigil

Vigil is a monthly maintenance check for Flutter apps you have already shipped. It compares each repo with store and SDK requirements you have approved, and it files news snippets for you to accept or dismiss. It does not open pull requests and it does not replace Dependabot or Sentry.

A scan never edits `requirements.yaml`. Fetched pages can only add proposals. You move a proposal into the requirements file with `vigil review`.

## Install on Fedora

Install Python tooling and the tray libraries:

```bash
sudo dnf install python3 pipx python3-gobject libappindicator-gtk3 gnome-shell-extension-appindicator
```

From this repository:

```bash
./packaging/install.sh
```

Or, if `vigil` is already on your `PATH`:

```bash
vigil desktop
```

That installs:

- **Apps grid:** search for **Vigil**. Opening it shows the latest report. Right-click (or long-press) also offers Run scan, Review proposals, Show tray icon, and Open reports folder.
- **Top bar:** a colored tray icon (green / amber / red). Click **Open latest report**, or use Run scan now. GNOME needs the AppIndicator extension for that icon to appear next to Wi-Fi and volume.
- **Monthly timer:** `vigil-scan.timer` runs `vigil scan` on the first of each month.
- **Notifications:** a scan that is not ok stays in the clock menu with **Open report**.

The script installs Vigil with pipx when `pipx` is on `PATH`, otherwise into `~/.local/share/vigil/venv` and links `~/.local/bin/vigil`. Running it again upgrades the install and leaves your config in place.

If `vigil` is not found after a venv install, add `~/.local/bin` to `PATH`.

Log out and back in once so the tray starts, or run `vigil tray` yourself.

## Where files live

| What | Path |
| --- | --- |
| Config | `~/.config/vigil/` |
| Snapshots, log, `status.json` | `~/.local/state/vigil/` |
| HTML reports | `~/.local/share/vigil/reports/` |

`VIGIL_CONFIG_DIR`, `VIGIL_STATE_DIR`, and `VIGIL_REPORTS_DIR` override those for tests. `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and `XDG_DATA_HOME` are honored.

## Monthly use

1. The `vigil-scan.timer` user unit runs `vigil scan` on the first of each month. `Persistent=true` means a missed run happens at the next boot.
2. Open the report from the apps grid (**Vigil**), the tray (**Open latest report**), the clock-menu notification (**Open report**), or `vigil open`. The file is also `~/.local/share/vigil/reports/latest.html`.
3. Run `vigil review`. For each proposal, accept it (you type the field and value), dismiss it, or skip it. When nothing is left pending, `last_verified` moves to today.
4. `vigil status` prints the last `status.json` summary.

A degraded scan still exits 0. Vigil exits non-zero only when it crashes. The log is `~/.local/state/vigil/vigil.log`. Add `--verbose` to mirror it to the terminal.

A desktop notification is sent when the result is not ok. It stays in the clock menu and can open the report. Set `notify: false` in `settings.yaml` to turn that off. `notify-send` has to be installed (`libnotify`).

## Config

Example files live in `src/vigil/examples/` and are copied by `vigil init`.

`vigil projects` opens a folder list, starting in your home directory. Enter opens the highlighted folder so you can look further. Space means the search stops at that folder. **Search this folder** is the one you are already in. Backspace goes up. `/` lets you type a path, and `documents\github` still finds `~/Documents/github`. The scan lists each Flutter project once and does not also list packages or example apps inside it. It then shows a checklist. Space toggles a project. Enter saves the checked projects into `repos.yaml`. Projects already on the list stay checked. A Flutter SDK checkout inside that folder is skipped.

```
[ ] abductonomics    android, ios
[ ] bottled_star    android
[X] craterfall    android, ios
```

`repos.yaml` is that saved list. `priority` is `high`, `normal`, or `low` and only changes report order. Run `vigil projects` again to change the selection. `vigil projects --dir /some/folder` scans a different folder and remembers it.

`requirements.yaml` is the only file repo checks trust. Each entry is a value plus an optional deadline and source URL:

```yaml
last_verified: 2026-10-21
android:
  target_api_min: {value: 36, deadline: "2026-08-31", source: https://example.test}
ios:
  min_xcode: {value: "26", deadline: "2026-04-28", source: https://example.test}
  min_deployment_target: {value: "13.0", source: https://example.test}
flutter:
  recommended_stable: {value: "3.47.7", source: https://example.test}
```

The copy `vigil init` writes was taken from public pages on 2026-10-21 (Play target API 36, Xcode 26, iOS 13, Flutter stable 3.47.7). It is not refreshed from the network. `vigil review` rewrites this file and drops comments.

`requirements.pending.yaml` holds proposals (`pending`, `accepted`, or `dismissed`). Dismissed and accepted quotes are not proposed again.

`expiries.yaml` is yours to edit. Vigil warns at 60 days and marks 14 days, or anything already expired, as action.

```yaml
expiries:
  - app: my_app
    item: Apple distribution certificate
    expires: "2027-03-01"
    notes: Renew in the Apple Developer portal
```

`settings.yaml` selects `notify` and `extractor`. The only extractor in v1 is `keyword`.

### Sources

`sources.yaml` lists RSS/Atom (`type: rss`), JSON, and HTML pages. URLs were checked on 2026-10-21:

- Apple Developer News RSS works.
- Apple Upcoming Requirements works.
- `https://android-developers.googleblog.com/feeds/posts/default` redirects to `https://developer.android.com/static/blog/atom.xml`. The example uses the destination.
- `https://support.google.com/googleplay/android-developer/answer/11926878` returns 404 to HEAD and 200 to GET. Vigil uses GET. The Android docs page `https://developer.android.com/google/play/requirements/target-sdk` is included as well because it carries the same target API text.
- Flutter `releases_linux.json` works. GitHub Atom feeds for Flutter and the Dart SDK work and are read as `rss`.

An empty `keywords` list uses the built-in phrases: target API level, targetSdk, API level, Xcode, SDK, "must be built with", deadline, required, minimum, deprecat, and "starting <month>".

## What a scan checks

- Flutter/Dart constraints in `pubspec.yaml`, plus `.fvmrc`, `.fvm/fvm_config.json`, or `.fvm/version`.
- `compileSdk` / `targetSdk` / `minSdk` in `android/app/build.gradle` or `build.gradle.kts`. `flutter.targetSdkVersion` and the same for compile and min are reported as inherited. Vigil reads the number from that repo's Flutter SDK (`android/local.properties`, `.fvm/flutter_sdk`, or `FLUTTER_ROOT`) and does not guess when the SDK is missing. It will not substitute a different `flutter` on `PATH` while an FVM pin is set.
- `IPHONEOS_DEPLOYMENT_TARGET` and the Podfile `platform :ios` line. The lower number is the one that is compared.
- `flutter pub outdated --json` when `flutter` is on `PATH`, plus the pub.dev API for each direct dependency (discontinued, replaced, retracted). One broken repo does not stop the others.
- Expiry dates.

Below a minimum is an action item, and the line includes the deadline when there is one ("due in 41 days", or "overdue by N days"). Meeting a minimum whose deadline is still ahead and inside 60 days is also an action. A deadline that has already passed does not keep a compliant app on the list. An inherited SDK value that could not be resolved is a watch item. Xcode is not detected on the machine; a future `ios.min_xcode` deadline inside 60 days is called out once, globally.

The drift table highlights a value when it is not the majority across apps that have one.

## When something upstream is unreachable

The report banner lists the failure and the status is `degraded`. That includes a page that changed but matched no keyword: the snapshot is left unchanged so the warning stays until the text yields a proposal or you change the source. A quiet "all clear" is not used to paper over a failed fetch.

## Commands

```bash
vigil init
vigil projects
vigil scan
vigil review
vigil status
vigil open
vigil tray
vigil desktop
vigil --verbose scan
```

`vigil scan` keeps one line on screen and rewrites it as it goes: `Scanning yetimatch (4 of 10 projects)`. The requirement pages use the same line before the projects start.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Tests use fixture repos and recorded responses. They do not touch the network.

## Later, not in v1

`Extractor.extract(changed_text, source)` is the seam for a local model. Register it in `get_extractor` and set `extractor` in `settings.yaml`. `external_alert_counts()` in `scan.py` is the seam for a Dependabot or Sentry count. Neither is implemented.
