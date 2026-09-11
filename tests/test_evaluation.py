from __future__ import annotations

from pathlib import Path

import pytest

from emergent_rpg.evaluation.harness import run_consistency_evaluation


def test_seeded_evaluation_is_reproducible(tmp_path: Path) -> None:
    first = run_consistency_evaluation(
        tmp_path / "first.db",
        turns=60,
        seed=12345,
        checkpoint_interval=20,
    )
    second = run_consistency_evaluation(
        tmp_path / "second.db",
        turns=60,
        seed=12345,
        checkpoint_interval=20,
    )

    assert first == second
    assert first.passed
    assert first.accepted_turns == 60
    assert first.checkpoint_turns == [20, 40, 60]


def test_mixed_scenario_exercises_rejection_and_multiple_action_kinds(tmp_path: Path) -> None:
    report = run_consistency_evaluation(
        tmp_path / "mixed.db",
        turns=80,
        seed=20260911,
        checkpoint_interval=25,
    )

    assert report.passed
    assert report.rejected_actions >= 2
    assert report.submitted_actions > report.accepted_turns
    assert report.persisted_turn_count == report.submitted_actions
    assert report.episode_count == report.accepted_turns
    assert report.action_counts.get("move", 0) > 0
    assert report.action_counts.get("inspect", 0) > 0
    assert report.action_counts.get("wait", 0) > 0
    assert report.replay_equal
    assert report.state_valid
    assert report.clock_monotonic
    assert report.player_knowledge_monotonic
    assert report.event_log_monotonic
    assert report.item_ownership_valid
    assert report.unique_event_ids


def test_evaluation_report_is_machine_readable_json(tmp_path: Path) -> None:
    report = run_consistency_evaluation(
        tmp_path / "json.db",
        turns=10,
        seed=7,
        checkpoint_interval=4,
    )
    payload = report.model_dump_json()

    assert '"passed":true' in payload
    assert '"accepted_turns":10' in payload
    assert '"scenario":"seeded-mixed-actions-v1"' in payload


def test_evaluation_refuses_to_overwrite_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "existing.db"
    path.write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        run_consistency_evaluation(path, turns=1)


def test_evaluation_validates_positive_limits(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="turns must be positive"):
        run_consistency_evaluation(tmp_path / "zero.db", turns=0)
    with pytest.raises(ValueError, match="checkpoint_interval must be positive"):
        run_consistency_evaluation(
            tmp_path / "interval.db",
            turns=1,
            checkpoint_interval=0,
        )
