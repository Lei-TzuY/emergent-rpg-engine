from emergent_rpg.evaluation.autonomy import run_autonomy_integration_evaluation


def test_autonomy_integration_evaluation_exercises_cross_subsystem_workflow(tmp_path) -> None:
    report = run_autonomy_integration_evaluation(tmp_path / "autonomy.db", rounds=2)

    assert report.passed is True, report.failures
    assert report.replay_equal is True
    assert report.state_valid is True
    assert report.unique_event_ids is True
    assert report.item_ownership_valid is True
    assert report.private_fact_isolated is True
    assert all(report.milestones.values()), report.milestones
    assert report.event_type_counts["player_item_given"] >= 1
    assert report.event_type_counts["npc_fact_shared"] >= 2
    assert report.event_type_counts["npc_item_delivered"] >= 1
    assert report.event_type_counts["simulation_cycle_processed"] >= 1
