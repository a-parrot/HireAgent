# 招聘 Agent 与节点目录

当前保留三个 Agent：recruitment_agent、resume_evaluation_agent、interview_agent。原 import_agent 和 evaluation_review_agent 的职责统一并入 resume_evaluation_agent；每个节点一个 Python 文件。

```text
agents/
├── recruitment_agent/
│   ├── recruitment_graph.py
│   ├── recruitment_state.py
│   └── nodes/
│       ├── parse_pdf.py            # 等待导入完成并交接全文
│       └── human_review.py         # 人工中断与恢复
├── resume_evaluation_agent/
│   ├── agent.py                    # 模型角色类的公共导入
│   ├── import_graph.py
│   ├── import_state.py
│   ├── decision.py                 # 共享的评分/证据计算工具
│   ├── scoring.py                  # 新流程版本、条件和证据工具
│   └── nodes/
│       ├── prepare_import.py       # PDF 格式和 SHA 校验
│       ├── parse_pdf.py            # 本地提取全文，保存独立快照
│       ├── save_import_result.py   # 确认解析产物
│       ├── screen_hard_conditions.py # 硬条件筛选，明确不合格结束
│       ├── extract_scoring_evidence.py # 匹配评分项和原文
│       ├── calculate_score.py      # 命中赋固定分，否则为 0
│       ├── analyze_resume.py       # 历史流程：提取事实与原文证据
│       ├── evaluate_candidate.py   # 按岗位规则评分
│       ├── route_candidate.py      # 代码求和、阈值分流
│       ├── review_evaluation.py    # 临界或存疑结果二次复核
│       └── summarize_result.py     # 汇总复核结果并交人工
└── interview_agent/
    ├── agent.py
    └── nodes/
        ├── auto_approve.py         # 面试准入与审计
        ├── auto_schedule.py        # 管理页按岗位/选择范围高分自动排期
        └── schedule_ready.py       # 统一排期与候补
```

新评估采用硬条件优先流程：screen_hard_conditions 明确不合格直接结束；否则 extract_scoring_evidence 提取评分项证据，calculate_score 由代码对命中项赋配置分值，未命中项赋 0，再按阈值分流。硬条件信息不足保留待核实状态，最终进入人工审核。两个语义节点各有独立提示词，calculate_score 不调用模型。

新建评估快照带 evaluation_flow=hard_conditions_verified_v2：parse_pdf → screen_hard_conditions → verify_hard_conditions → extract_scoring_evidence → verify_scoring_evidence → calculate_score → 自动准入/人工审核/结束。硬条件复核不通过时提前结束。通用工作年限按原文辅助核验，评分专业领域另行校验，复核判断冲突则保留人工核实。

历史 hard_conditions_first_v1 快照保留原硬条件优先路径；无标记记录继续 analyze_resume/evaluate_candidate/route_candidate/review_evaluation/summarize_result 原路径，用于恢复历史检查点，不自动重算旧评分。三个 Agent 目录保留不变，新节点均位于 resume_evaluation_agent/nodes/。

节点提供 async run(runtime, state)；需要写回候选人的节点额外提供 save(candidate, output, config)。nodes/__init__.py 显式注册节点。agent.py 只提供公共导入/薄封装，Runtime 仅管理生命周期、并发、事务、审计和恢复，不集中分支实现节点业务。schedule_ready 是评估完成/恢复后的回调，单独保存在自己的节点文件中。

解析使用本地 PyMuPDF，不保存新页码。历史任务在 file_import_tasks，评估事件在 events，节点结果在 node_executions，正文按 parsed/<file_id>/imports/<task_id>/ 独立保存。无需数据库迁移；测试不发送真实简历。

高分自动排期节点复用准入审计和预约服务，只使用实际配置的未来时段；补充时段后可自动将已准入候补安排。无效评估软删除保留事件审计，各业务查询与恢复过程统一使用 repositories/evaluation_repo/visibility.py 判断可见性，不物理删除原件或检查点。
