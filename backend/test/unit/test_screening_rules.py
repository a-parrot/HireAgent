from app.agents.resume_evaluation_agent.scoring import blocking_conditions


def test_passed_or_group_does_not_add_its_failed_alternative_to_rejection_reason():
    tree = {
        "operator": "all",
        "items": [
            {"operator": "any", "items": [{"id": "work"}, {"id": "direct"}]},
            {"id": "management"},
        ],
    }
    assert blocking_conditions(
        tree,
        {
            "work": "satisfied",
            "direct": "unsatisfied",
            "management": "unsatisfied",
        },
    ) == {"management"}


def test_proven_failure_still_blocks_when_another_required_condition_is_unknown():
    tree = {"operator": "all", "items": [{"id": "field"}, {"id": "management"}]}
    assert blocking_conditions(
        tree, {"field": "unsatisfied", "management": "unknown"}
    ) == {"field"}
