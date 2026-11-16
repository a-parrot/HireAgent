"""Extract local PDF text and save this import task's independent snapshot."""

from app.services.resume_service.resumes import parse_pdf


async def run(runtime, state):
    return {
        "pages": await parse_pdf(
            runtime.db,
            runtime.config,
            state["file_id"],
            finalize=False,
            task_id=state["task_id"],
        )
    }
