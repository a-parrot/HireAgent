from app.agents.interview_agent.nodes import auto_approve
from app.agents.recruitment_agent.nodes import parse_pdf
from app.agents.resume_evaluation_agent.nodes import (
    analyze_resume,
    calculate_score,
    evaluate_candidate,
    extract_scoring_evidence,
    review_evaluation,
    route_candidate,
    screen_hard_conditions,
    summarize_result,
    verify_hard_conditions,
    verify_scoring_evidence,
)

NODES = {
    "verify_hard_conditions": verify_hard_conditions,
    "verify_scoring_evidence": verify_scoring_evidence,
    "screen_hard_conditions": screen_hard_conditions,
    "extract_scoring_evidence": extract_scoring_evidence,
    "calculate_score": calculate_score,
    "parse_pdf": parse_pdf,
    "analyze_resume": analyze_resume,
    "evaluate_candidate": evaluate_candidate,
    "route_candidate": route_candidate,
    "review_evaluation": review_evaluation,
    "summarize_result": summarize_result,
    "auto_approve": auto_approve,
}
