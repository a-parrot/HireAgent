# Slide Outline

## Meta
- Topic: HireAgent——基于多智能体框架的招聘自动化系统（毕业答辩）
- Scenario: 毕业答辩 / 技术答辩，面向评审老师的项目汇报
- Content Source: provided（需求分析 PDF + docs/项目汇报概要.md + 后端代码结构）
- Style: 学术深蓝 — 深海军蓝 (#0A1F44 系) 底色或浅底深蓝主色，白色/浅色大字标题，克制的几何装饰与节点连线图示，单一青蓝色强调；衬线感大标题 + 无衬线正文，答辩场合的稳重感
- Slide Count: 12
- Generated At: 2026-11-16T13:10:00+08:00

## Source Materials
- 《AI_Agent多智能体招聘题目.pdf》：任务目标、岗位与筛选规则、评分维度（钢结构MiC 30分等8项、推荐线75/复核线60）、工作流与输出要求、交付边界
- docs/项目汇报概要.md：项目定位、五大功能模块、技术选型（LangGraph/MySQL/FastAPI/Vue3）、三大Agent角色、五个工作流结构、汇报重点
- backend 代码结构：agents/api/services/repositories/prompts 分层

## Slide-by-Slide Outline
1. **Slide 1 — 封面 (Cover)** — HireAgent：基于多智能体框架的招聘自动化系统 | 副标题：从简历解析到面试排期的全流程智能协作 | Layout hint: L01 封面大标题+装饰节点图 | Chart: no
2. **Slide 2 — 目录 (Agenda)** — 研究背景 / 系统设计 / 多智能体架构 / 核心工作流 / 功能实现 / 总结展望 | Layout hint: L02 编号目录 | Chart: no
3. **Slide 3 — 项目背景与任务目标 (Background)** — 214份PDF简历需完成解析→筛选→评分→人工复核→排期→会议通知；难点：证据可追溯、人工可中断恢复、规则不随编辑漂移 | Layout hint: L03 左文右数据卡 | Chart: no
4. **Slide 4 — 岗位规则与评分体系 (Rules)** — 目标岗位：海外项目负责人（钢结构/MiC）；硬条件筛查 + 8维评分（MiC经验30/全流程15/海外15/管理15/质量10/沟通5/规模5/适配5）；≥75推荐、60–74复核、<60不推荐；规则版本快照 | Layout hint: L10 双栏+评分条形图 | Chart: yes（评分维度条形图）
5. **Slide 5 — 系统总体架构 (Architecture)** — 前后端分离：Vue3+TS+Element Plus / FastAPI+Pydantic 分层（API/Service/Repository/Client）/ LangGraph 编排 + MySQL Checkpointer / MySQL 8.4 + 本地文件存储 | Layout hint: L05 分层架构图 | Chart: yes（架构示意）
6. **Slide 6 — 多智能体设计 (Agents)** — 三大角色：招聘编排 recruitment_agent（主流程分支控制）、简历评估 resume_evaluation_agent（硬条件/证据/计分）、面试 interview_agent（自动准入与排期组织）；职责划分而非独立进程；模型找证据、程序算分 | Layout hint: L06 三卡片+协作连线 | Chart: yes（Agent协作图）
7. **Slide 7 — 核心工作流：硬条件优先评估 (Workflow 1)** — parse_pdf → screen_hard_conditions → verify_hard_conditions → extract/verify_scoring_evidence → calculate_score → 分流（自动准入/人工复核/不推荐）；二次复核防漏匹配；LangGraph interrupt 挂起恢复 | Layout hint: L07 横向流程节点图 | Chart: yes（流程图）
8. **Slide 8 — 核心工作流：人工复核与恢复 (Workflow 2)** — interrupt 挂起 → 人工批准/暂缓/补充说明 → 保存审核人与理由 → 一致性校验 → 恢复主图 → 检查面试安排；版本校验防过期覆盖 | Layout hint: L07 流程+三决策卡 | Chart: yes（流程图）
9. **Slide 9 — 核心工作流：面试排期与会议通知 (Workflow 3)** — 排期：候选人为中心、批量连续预约45分钟、跨批次冲突校验、同事务回滚、按总分>MiC>海外>管理排序；通知：预览→编辑→人工授权→幂等执行→对账；边界：会议/通知适配器待接入真实平台 | Layout hint: L08 左右双栏流程 | Chart: yes（时序/流程示意）
10. **Slide 10 — 功能实现与可靠性设计 (Features)** — 五大功能：岗位规则管理（版本快照）、简历导入（SHA-256去重+解析快照）、评估与复核（证据高亮定位）、排期管理、日志追溯；可靠性：运行锁/候选人锁/并发信号量/事务一致/失败重试 | Layout hint: L09 bento 网格功能卡 | Chart: no
11. **Slide 11 — 总结与未来展望 (Summary & Outlook)** — 已达成：可运行的多智能体工作流、证据可追溯、人工可中断恢复、规则版本化；展望：扫描件OCR接入、真实会议/通知平台对接（腾讯会议/企业微信）、多岗位并行与分布式多实例、候选人端自助查询、评估效果A/B与召回率优化 | Layout hint: L11 左总结右展望 | Chart: no
12. **Slide 12 — 致谢/Q&A (End)** — 恳请各位老师批评指正 | Layout hint: L01 封面式收尾 | Chart: no

## Visual Rhythm Notes
- Chart-bearing slides at positions: 4, 5, 6, 7, 8, 9
- Dark accent slides（深蓝底）: 1, 5, 12；其余浅底深蓝主色
- Slides are viewed on large screens, often from a distance. Small text is unreadable. Every text element must be sized generously and fill its container space rather than floating in emptiness.
- Slides should feel visually rich and layered, not like text pasted on rectangles. Decorative elements add polish, and SVG charts communicate data far more effectively than text or numbers alone.
