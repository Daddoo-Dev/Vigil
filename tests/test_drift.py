from vigil.drift import DriftInput, build_drift, outlier_mask


def test_unique_majority_marks_only_the_odd_value():
    assert outlier_mask(["35", "35", "34", "—"]) == [False, False, True, False]


def test_a_tie_marks_every_filled_cell():
    assert outlier_mask(["1.0.0", "2.0.0"]) == [True, True]


def test_drift_orders_high_priority_first_and_shares_packages():
    table = build_drift(
        [
            DriftInput("Later", "low", "3.24.0", ">=3.5.0", "34", "12.0", {"http": "1.0.0"}),
            DriftInput("First", "high", "3.47.7", ">=3.5.0", "36", "13.0", {"http": "1.2.0"}),
            DriftInput("Solo", "normal", "3.47.7", ">=3.5.0", "36", "13.0", {"other": "9.0.0"}),
        ]
    )
    assert table.columns[:4] == ["Flutter", "Dart", "targetSdk", "iOS"]
    assert "http" in table.columns
    assert "other" not in table.columns
    assert [row.name for row in table.rows] == ["First", "Solo", "Later"]
    flutter_cells = [row.cells[0] for row in table.rows]
    assert flutter_cells[2].text == "3.24.0"
    assert flutter_cells[2].outlier is True
    assert flutter_cells[0].outlier is False
