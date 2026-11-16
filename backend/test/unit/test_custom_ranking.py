from types import SimpleNamespace

from app.services.schedule_service.scheduling import ranking_key


def candidate(cid, total, overseas, management):
    return SimpleNamespace(
        id=cid,
        total_score=total,
        dimension_scores=[
            {"dimension_id": "overseas", "score": overseas},
            {"dimension_id": "management", "score": management},
        ],
    )


def test_configured_priority_changes_equal_total_order():
    a, b = candidate(1, 80, 15, 0), candidate(2, 80, 0, 15)
    assert sorted(
        [a, b], key=lambda c: ranking_key(c, ["total_score", "overseas", "management"])
    ) == [a, b]
    assert sorted(
        [a, b], key=lambda c: ranking_key(c, ["total_score", "management", "overseas"])
    ) == [b, a]


def test_total_score_precedes_dimensions_and_complete_ties_use_id():
    a, b = candidate(1, 80, 0, 0), candidate(2, 79, 15, 15)
    assert ranking_key(a, ["total_score", "overseas"]) < ranking_key(
        b, ["total_score", "overseas"]
    )
    assert ranking_key(a, ["total_score"]) < ranking_key(
        candidate(3, 80, 15, 15), ["total_score"]
    )
