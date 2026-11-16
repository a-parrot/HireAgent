from app.agents.resume_evaluation_agent.nodes import (
    parse_pdf,
    prepare_import,
    save_import_result,
)

IMPORT_NODES = {
    "prepare_import": prepare_import,
    "parse_pdf": parse_pdf,
    "save_import_result": save_import_result,
}
