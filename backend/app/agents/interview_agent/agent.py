"""Public facade for interview admission and scheduling nodes."""

from app.agents.interview_agent.nodes.auto_approve import approve
from app.agents.interview_agent.nodes.schedule_ready import schedule_ready


class InterviewAgent:
    async def approve(self, db, candidate_id):
        return await approve(db, candidate_id)

    async def schedule_ready(self, db, batch_id):
        return await schedule_ready(db, batch_id)
