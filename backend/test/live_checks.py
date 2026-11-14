"""只有显式选择连通性文件或设置开关时，pytest 才访问真实服务。"""

import os
from pathlib import Path

import pytest


def require_live_check(request, filename, environment_flag):
    target = Path(filename).resolve()
    directory = request.config.invocation_params.dir
    selected = any(
        (directory / argument.split("::", 1)[0]).resolve() == target
        for argument in request.config.args
    )
    if not selected and os.getenv(environment_flag) != "1":
        pytest.skip(f"单独运行 {target.name} 或设置 {environment_flag}=1")
