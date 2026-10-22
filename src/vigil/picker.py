"""Checkbox list for choosing which discovered projects to monitor."""

from __future__ import annotations

from vigil.discover import Project


def row_text(project: Project) -> str:
    box = "[X]" if project.selected else "[ ]"
    platforms = ", ".join(project.platforms)
    if platforms:
        return f"{box} {project.label}    {platforms}"
    return f"{box} {project.label}"


def run_picker(projects: list[Project]) -> list[Project] | None:
    """Show the checklist. Return the projects when saved, or None when cancelled."""
    import curses

    if not projects:
        return []
    outcome: dict[str, bool] = {"saved": False}

    def draw(stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)
        cursor = 0
        top = 0
        while True:
            height, width = stdscr.getmaxyx()
            if width < 2 or height < 3:
                key = stdscr.getch()
                if key in (ord("q"), 27):
                    return
                continue
            visible = height - 2
            if cursor < top:
                top = cursor
            elif cursor >= top + visible:
                top = cursor - visible + 1
            stdscr.erase()
            stdscr.addnstr(0, 0, "Space toggles. Enter saves. q cancels.", width - 1, curses.A_BOLD)
            for row, project in enumerate(projects[top : top + visible]):
                index = top + row
                line = row_text(project)
                attr = curses.A_REVERSE if index == cursor else curses.A_NORMAL
                stdscr.addnstr(1 + row, 0, line, width - 1, attr)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord("k")):
                cursor = (cursor - 1) % len(projects)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = (cursor + 1) % len(projects)
            elif key == ord(" "):
                projects[cursor].selected = not projects[cursor].selected
            elif key in (curses.KEY_ENTER, 10, 13):
                outcome["saved"] = True
                return
            elif key in (ord("q"), 27):
                return

    curses.wrapper(draw)
    if outcome["saved"]:
        return projects
    return None
