import re

from app.core.errors import BusinessError
from app.prompts.prompt_loader import load_prompt, prompt_version
from app.schemas.agents import Analysis


def redact(text):
    return "\n".join(
        line
        for line in text.splitlines()
        if not re.search(r"性别|婚姻|婚育|民族|出生日期|出生年月|年龄", line)
    )


def document_chunks(pages, max_chars):
    # Pack the entire short resume into one request. Long documents split at headings/paragraphs.
    chunks, current, size = [], [], 0
    for page in pages:
        text = redact(page["text"])
        parts = (
            [text] if len(text) <= max_chars else re.split(r"(?m)(?=^#{1,6}\s)", text)
        )
        units = []
        for part in parts:
            units.extend(
                [part] if len(part) <= max_chars else re.split(r"\n\s*\n", part)
            )
        for part in units:
            if not part.strip():
                continue
            if len(part) > max_chars:
                # A PDF may extract an entire page as one paragraph. Keep all text,
                # prefer sentence/newline boundaries, and overlap hard boundaries.
                start = 0
                while start < len(part):
                    end = min(start + max_chars, len(part))
                    boundaries = list(re.finditer(r"[。！？.!?\n]", part[start:end]))
                    natural = boundaries and boundaries[-1].end() >= max_chars // 2
                    if end < len(part) and natural:
                        end = start + boundaries[-1].end()
                    if current:
                        chunks.append(current)
                        current, size = [], 0
                    chunks.append([{**page, "text": part[start:end]}])
                    if end == len(part):
                        break
                    start = end if natural else end - min(200, max_chars // 10)
                continue
            if current and size + len(part) > max_chars:
                chunks.append(current)
                current, size = [], 0
            current.append({**page, "text": part})
            size += len(part)
    if current:
        chunks.append(current)
    if not chunks:
        raise BusinessError("简历没有可用于分析的正文")
    return chunks


class ResumeAnalysisAgent:
    async def run(self, llm, rules, pages, max_chars):
        chunks = document_chunks(pages, max_chars)
        output = {"name": None, "facts": [], "evidence": [], "missing_fields": []}
        for index, chunk in enumerate(chunks):
            result = await llm.generate(
                load_prompt("resume_analysis"),
                {"rules": rules, "pages": chunk, "chunk_prefix": f"c{index}_"},
                Analysis,
            )
            output["name"] = output["name"] or result["name"]
            for key in ("facts", "evidence", "missing_fields"):
                output[key].extend(result[key])
        return output


async def run(runtime, state):
    rules = await runtime.rules(state["candidate_id"])
    return {
        "analysis": await ResumeAnalysisAgent().run(
            runtime.llm, rules, state["pages"], runtime.config.llm_document_chars
        )
    }


def save(candidate, output, config):
    result = output["analysis"]
    candidate.name = result["name"]
    candidate.extracted_facts, candidate.evidence = result["facts"], result["evidence"]
    candidate.model_id = config.llm_model
    candidate.prompt_versions = {
        **(candidate.prompt_versions or {}),
        "analysis": prompt_version("resume_analysis"),
    }
