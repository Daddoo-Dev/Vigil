from vigil.tray import backend_help, make_icon, tooltip


def test_icons_are_distinct_solid_circles():
    ok = make_icon("ok").getpixel((32, 32))
    action = make_icon("action").getpixel((32, 32))
    degraded = make_icon("degraded").getpixel((32, 32))
    unknown = make_icon("missing").getpixel((32, 32))
    assert ok == (46, 125, 50, 255)
    assert action[0] > action[2]
    assert degraded[0] > 150 and degraded[1] < 80
    assert unknown == (117, 117, 117, 255)
    assert len({ok, action, degraded, unknown}) == 4


def test_tooltip_and_backend_message():
    assert "no scan yet" in tooltip(None)
    assert "degraded" in tooltip({"state": "degraded", "action_count": 1})
    message = backend_help("linux")
    assert "python3-gobject" in message
    assert "libappindicator-gtk3" in message
    assert "gnome-shell-extension-appindicator" in message
    assert "pystray" in backend_help("windows")
