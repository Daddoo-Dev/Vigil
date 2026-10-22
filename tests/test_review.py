from datetime import date

from tests.conftest import write_yaml
from vigil.requirements import load_proposals, load_requirements
from vigil.review import run_review


def _input(answers: list[str]):
    pending = iter(answers)

    def read(_prompt: str = "") -> str:
        return next(pending)

    return read


def test_accept_writes_requirements_and_verifies_the_date(paths):
    write_yaml(paths.config_dir / "requirements.yaml", {})
    write_yaml(
        paths.config_dir / "requirements.pending.yaml",
        {
            "proposals": [
                {
                    "id": "abc",
                    "source_id": "play",
                    "found_at": "2026-10-21",
                    "quote": "Target API level 36.",
                    "snippet_url": "https://example.test/play",
                    "suggested_field": "android.target_api_min",
                    "suggested_value": "36",
                    "status": "pending",
                }
            ]
        },
    )
    lines: list[str] = []
    run_review(
        paths,
        date(2026, 10, 21),
        input_fn=_input(["a", "android.target_api_min", "36", "2026-12-01"]),
        output_fn=lines.append,
    )
    requirements = load_requirements(paths.config_dir / "requirements.yaml")
    assert requirements["android"]["target_api_min"]["value"] == 36
    assert requirements["android"]["target_api_min"]["deadline"] == "2026-12-01"
    assert requirements["android"]["target_api_min"]["source"] == "https://example.test/play"
    assert requirements["last_verified"] == "2026-10-21"
    assert load_proposals(paths.config_dir / "requirements.pending.yaml")[0].status == "accepted"
    assert any("2026-10-21" in line for line in lines)


def test_skip_leaves_last_verified_unset(paths):
    write_yaml(paths.config_dir / "requirements.yaml", {})
    write_yaml(
        paths.config_dir / "requirements.pending.yaml",
        {
            "proposals": [
                {
                    "id": "abc",
                    "source_id": "play",
                    "found_at": "2026-10-21",
                    "quote": "Target API level 36.",
                    "snippet_url": "https://example.test/play",
                    "suggested_field": None,
                    "suggested_value": None,
                    "status": "pending",
                }
            ]
        },
    )
    run_review(paths, date(2026, 10, 21), input_fn=_input(["s"]), output_fn=lambda _line: None)
    requirements = load_requirements(paths.config_dir / "requirements.yaml")
    assert "last_verified" not in requirements
    assert load_proposals(paths.config_dir / "requirements.pending.yaml")[0].status == "pending"


def test_empty_review_stamps_last_verified(paths):
    write_yaml(paths.config_dir / "requirements.yaml", {"flutter": {"recommended_stable": {"value": "3.47.7"}}})
    run_review(paths, date(2026, 10, 21), input_fn=_input([]), output_fn=lambda _line: None)
    requirements = load_requirements(paths.config_dir / "requirements.yaml")
    assert requirements["last_verified"] == "2026-10-21"
    assert requirements["flutter"]["recommended_stable"]["value"] == "3.47.7"
