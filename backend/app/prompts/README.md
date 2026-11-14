# 按功能组织的招聘提示词模板

参考 data_ask 的独立文件加载和 LangChain 模板渲染方式，实际只修改 HireAgent。模板格式为 .prompt，保留当前 app/prompts 目录，不依赖参考项目运行。

| 模板 | 只负责 | 动态输入 |
| --- | --- | --- |
| resume_analysis.prompt | 提取事实、原文证据、当前片段缺失项 | rules、pages、chunk_prefix |
| candidate_evaluation.prompt | 硬条件叶子判断、按手动标准逐项评分 | rules、facts、evidence |
| evaluation_review.prompt | 对照规则检查依据、矛盾及遗漏，提示人工核实 | rules、facts、evidence、evaluation |

每个模板分成两段：`--- INPUT ---` 之前是固定 system 职责和输出 Schema，之后是带占位符的 user 输入。prompt_loader.load_prompt 返回 ChatPromptTemplate；模型客户端通过 render_messages 将结构化参数序列化为 JSON，填入同名占位符，并填入 output_schema。插入的文本不会再次作为模板执行，因此正文中的花括号和疑似占位符保持原样。

rules 来自当前 batches.rule_snapshot，包含岗位信息、手动配置的 hard_conditions、dimensions、criteria、max_score、证据要求及两个总分阈值。不得改为读取岗位最新草稿，以免已开始批次的标准发生变化。

模板中不固定初始岗位、维度数量、分值或阈值。总分求和、硬条件组合和阈值过滤仍由 summarize_result 处理；即使模型看到了阈值，评分和复核角色也不代替程序决定最终分流，更不能代替人工批准。

只需替换规则配置，不必为每个岗位复制模板。编辑模板后重启后端使进程缓存更新；候选人按实际执行角色记录模板内容摘要版本。成功节点在恢复时复用既有产物，不因修改模板静默重评；希望完整按新模板重新评估时新建批次。

本次仅完成模板与调用链改造，不改变数据库，不把规则 JSON 编辑器宣称为已实现的可视化表单。测试使用构造的规则和隔离 HTTP，不调用真实模型、不发送真实简历。
