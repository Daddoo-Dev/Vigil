from vigil.snapshots import content_hash, diff_snapshot, load_snapshot, save_snapshot


def test_unchanged_text_is_not_a_diff():
    paragraphs = ["Alpha requirement.", "Beta note."]
    assert diff_snapshot(paragraphs, list(paragraphs)).changed is False


def test_only_added_paragraphs_are_returned():
    previous = ["Keep me.", "Remove me."]
    current = ["Keep me.", "A new store rule."]
    diff = diff_snapshot(previous, current)
    assert diff.changed is True
    assert diff.added == ["A new store rule."]


def test_whitespace_only_changes_do_not_count_as_added():
    previous = ["Target API level 35 is required."]
    current = ["Target   API level 35 is required."]
    assert diff_snapshot(previous, current).changed is False


def test_snapshot_round_trip(tmp_path):
    path = tmp_path / "snapshots" / "play.json"
    save_snapshot(path, ["One.", "Two."])
    assert load_snapshot(path) == ["One.", "Two."]
    assert content_hash(["One.", "Two."]) == content_hash(load_snapshot(path) or [])
