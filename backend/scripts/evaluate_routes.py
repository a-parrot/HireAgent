"""Synthetic rule-router benchmark, not a model or end-to-end accuracy claim."""

import json
from statistics import mean
from time import perf_counter

from app.agents.resume_evaluation_agent.decision import summarize
from test.unit.test_rules_and_model import inputs


def main():
    labels = ["recommended", "needs_review", "deferred"]
    matrix = [[0] * 3 for _ in labels]
    times = []
    cases = [
        (100, "recommended"),
        (75, "recommended"),
        (74, "needs_review"),
        (60, "needs_review"),
        (59, "deferred"),
        (0, "deferred"),
    ]
    for _ in range(100):
        for score, expected in cases:
            data = inputs(score)
            started = perf_counter()
            actual = summarize(*data)["recommendation"]
            times.append((perf_counter() - started) * 1000)
            matrix[labels.index(expected)][labels.index(actual)] += 1
    ordered = sorted(times)
    per_class = {}
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        precision = tp / sum(row[i] for row in matrix)
        recall = tp / sum(matrix[i])
        per_class[label] = dict(
            precision=precision,
            recall=recall,
            f1=2 * precision * recall / (precision + recall),
        )
    print(
        json.dumps(
            dict(
                scope="synthetic legacy rule routing only; no LLM, I/O or concurrency",
                unique_cases=len(cases),
                repetitions=100,
                labels=labels,
                confusion_matrix=matrix,
                accuracy=sum(matrix[i][i] for i in range(3)) / len(times),
                per_class=per_class,
                latency_ms=dict(
                    mean=mean(times),
                    **{
                        f"p{p}": ordered[int((len(times) - 1) * p / 100)]
                        for p in (50, 95, 99)
                    },
                ),
                llm_calls=0,
                tokens=0,
                semantic_accuracy=None,
                tool_routing_accuracy=None,
                structured_output_validity=None,
                ttft=None,
                concurrent_success_rate=None,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
