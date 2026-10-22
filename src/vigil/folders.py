"""Pick the folder Vigil scans. Arrow keys browse; a typed path is forgiving."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_HIDE = {"node_modules", "build", "Pods", "ephemeral"}


@dataclass(frozen=True)
class FolderRow:
    label: str
    path: Path
    scans: bool


def resolve_folder(raw: str, *, cwd: Path, home: Path) -> Path | None:
    """Find a folder from loose input.

    Accepts ``~``, backslashes, and a different capitalisation. A relative path
    is tried from the current directory and then from the home directory, so
    ``documents\\github`` still finds ``~/Documents/github``.
    """
    text = raw.strip().strip("\"'").replace("\\", "/")
    if not text:
        return None
    if text == "~":
        text = str(home)
    elif text.startswith("~/"):
        text = str(home / text[2:])
    path = Path(text)
    bases = [path] if path.is_absolute() else [cwd / path, home / path]
    for base in bases:
        match = _match_case(base)
        if match is not None and match.is_dir():
            return match.resolve()
    return None


def display_path(path: Path, home: Path) -> str:
    try:
        relative = path.resolve().relative_to(home.resolve())
    except ValueError:
        return str(path)
    if relative.as_posix() == ".":
        return "~"
    return "~/" + relative.as_posix()


def folder_rows(current: Path) -> list[FolderRow]:
    """The current folder, a parent link, then the child folders."""
    rows = [FolderRow("Search this folder", current, scans=True)]
    parent = current.parent
    if parent != current:
        rows.append(FolderRow("..", parent, scans=False))
    children: list[Path] = []
    try:
        for child in current.iterdir():
            if child.name.startswith(".") or child.name in _HIDE:
                continue
            if child.is_dir():
                children.append(child)
    except OSError:
        return rows
    children.sort(key=lambda child: child.name.casefold())
    rows.extend(FolderRow(f"{child.name}/", child, scans=False) for child in children)
    return rows


def opening_cursor(rows: list[FolderRow]) -> int:
    """Land on the first real folder so Enter opens it instead of searching by accident."""
    for index, row in enumerate(rows):
        if not row.scans and row.label != "..":
            return index
    return 0


def activate(location: Path, cursor: int, choose: bool) -> tuple[Path, int, Path | None]:
    """Enter opens the highlighted folder. Space ends the search at that folder.

    The "Search this folder" row is the directory you are already in. Enter and
    Space both accept it, because there is nowhere further to open.
    """
    rows = folder_rows(location)
    if not rows:
        return location, 0, None
    cursor = min(max(cursor, 0), len(rows) - 1)
    row = rows[cursor]
    if choose or row.scans:
        return location, cursor, row.path.resolve()
    opened = row.path
    return opened, opening_cursor(folder_rows(opened)), None


def run_folder_picker(start: Path | None = None) -> Path | None:
    """Browse from ``start`` (home, when omitted). Return the folder to scan."""
    import curses

    home = Path.home()
    current = (start or home).expanduser()
    if not current.is_dir():
        current = home
    chosen: dict[str, Path | None] = {"path": None}

    def draw(stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        cursor = opening_cursor(folder_rows(current))
        location = current
        while True:
            rows = folder_rows(location)
            if cursor >= len(rows):
                cursor = max(0, len(rows) - 1)
            height, width = stdscr.getmaxyx()
            if width < 2 or height < 4:
                if stdscr.getch() in (ord("q"), 27):
                    return
                continue
            visible = height - 3
            top = min(cursor, max(0, len(rows) - visible))
            if cursor < top:
                top = cursor
            stdscr.erase()
            title = f"Projects live in: {display_path(location, home)}"
            stdscr.addnstr(0, 0, title, width - 1, curses.A_BOLD)
            stdscr.addnstr(
                1,
                0,
                "Enter opens. Space searches that folder. Backspace up. q cancels.",
                width - 1,
            )
            for row_index, row in enumerate(rows[top : top + visible]):
                index = top + row_index
                attr = curses.A_REVERSE if index == cursor else curses.A_NORMAL
                stdscr.addnstr(2 + row_index, 0, row.label, width - 1, attr)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")) and rows:
                cursor = (cursor - 1) % len(rows)
            elif key in (curses.KEY_DOWN, ord("j")) and rows:
                cursor = (cursor + 1) % len(rows)
            elif key in (curses.KEY_ENTER, 10, 13, ord(" ")) and rows:
                location, cursor, picked = activate(location, cursor, choose=key == ord(" "))
                if picked is not None:
                    chosen["path"] = picked
                    return
            elif key in (curses.KEY_BACKSPACE, curses.KEY_LEFT, 127, 8):
                parent = location.parent
                if parent != location:
                    location = parent
                    cursor = opening_cursor(folder_rows(location))
            elif key == ord("/"):
                typed = _read_path(stdscr)
                if typed is None:
                    continue
                match = resolve_folder(typed, cwd=location, home=home)
                if match is None:
                    _flash(stdscr, f"No folder matches {typed}")
                    continue
                location = match
                cursor = opening_cursor(folder_rows(location))
            elif key in (ord("q"), 27):
                return

    curses.wrapper(draw)
    return chosen["path"]


def _read_path(stdscr) -> str | None:
    import curses

    height, width = stdscr.getmaxyx()
    curses.curs_set(1)
    curses.echo()
    try:
        stdscr.addnstr(height - 1, 0, "Path: ", width - 1)
        stdscr.clrtoeol()
        stdscr.refresh()
        raw = stdscr.getstr(height - 1, 6, max(1, width - 8))
    except curses.error:
        return None
    finally:
        curses.noecho()
        curses.curs_set(0)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _flash(stdscr, message: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.addnstr(height - 1, 0, message, width - 1)
    stdscr.clrtoeol()
    stdscr.refresh()
    stdscr.getch()


def _match_case(path: Path) -> Path | None:
    parts = path.parts
    if not parts:
        return None
    if path.is_absolute():
        current = Path(parts[0])
        remaining = parts[1:]
    else:
        current = Path.cwd()
        remaining = parts
    if not current.exists():
        return None
    for part in remaining:
        direct = current / part
        if direct.exists():
            current = direct
            continue
        if not current.is_dir():
            return None
        found = None
        try:
            for child in current.iterdir():
                if child.name.casefold() == part.casefold():
                    found = child
                    break
        except OSError:
            return None
        if found is None:
            return None
        current = found
    return current
