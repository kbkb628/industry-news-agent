# 行业资讯结构化推送智能体 MVP 设计文档

## 1. 文档目的

本文档用于冻结 `E:\bgagent2` 目录下“行业资讯结构化推送智能体”的首轮开发范围、架构边界、接口契约和验收口径。

本文档以 [DEVELOPMENT_GUIDE.md](E:/bgagent2/DEVELOPMENT_GUIDE.md) 为最高策略依据。开发过程中必须严格遵守指导文档，不得擅自改变技术策略、阶段划分、能力边界和面试表达边界。

## 2. 开发约束

本轮开发必须遵守以下约束：

1. 仅开发指导文档中的 `MVP` 闭环。
2. 不提前实现第二阶段能力，不把第二阶段能力包装成已完成能力。
3. 必须使用真实 `PostgreSQL + Redis`，不得用 SQLite、纯内存持久化替代数据库事实源。
4. `LLM` 先使用 `MockLLM` 跑通闭环，但必须保留可替换接口。
5. 对外提供 `FastAPI + Swagger`，并补充极简 `HTML` 管理页。
6. 代码结构必须与指导文档的推荐目录和分层思想保持一致。
7. 不允许假候选池、假工具调用、假推送历史、假 RAG、假持久化。
8. 所有降级、失败和回退路径必须显式记录，不能吞错。

## 3. 本轮目标

本轮目标是在当前空目录下，从零搭建一个真实可运行的单体后端系统，完成以下闭环：

`创建主题 -> 手动触发监控 -> 关键词扩展 -> RSS/mock_search 召回 -> 正文抓取或摘要降级 -> 结构化抽取 -> 去重 -> 价值评分 -> 推送决策 -> 落库 -> 事件记录 -> 规则评估 -> API/HTML 可查询`

系统必须真实可运行、可观测、可追溯，但不追求第二阶段能力。

## 4. 非目标

本轮明确不做以下内容：

- 真实 `MCP Server` 接入
- 真实 `Playwright MCP`
- `Redis Stream`
- `Elasticsearch / OpenSearch`
- `embedding + BM25 + rerank`
- `LLM-as-Judge`
- `React + Vite` 管理后台
- 多进程 Worker 架构
- Webhook / Slack / 企业微信 / 邮件通知通道

以上内容只允许保留接口、抽象层或后续扩展点，不允许在文档或代码中描述为“已完成能力”。

## 5. 推荐实现方案

采用“单体服务 + 明确分层接口”的方案：

- 运行形态为单个 `FastAPI` 进程。
- 同一进程内承载 API、HTML 页面、APScheduler、LangGraph 编排、Repository、Redis 协调。
- 从首轮开始冻结 `ToolGateway`、`LLMClient`、`Repository` 三类核心接口。
- 在单体部署的前提下，为第二阶段真实 MCP、队列和检索增强保留清晰边界。

选择该方案的原因：

- 它符合指导文档先做真实 MVP 闭环的要求。
- 它比“直接双进程 + 队列”的起步方式更适合当前空仓库快速落地。
- 它避免后续因边界混乱而整体返工。

## 6. 系统模块边界

### 6.1 api

职责：

- 暴露主题、运行、候选、推送、事件、评估接口
- 提供极简 HTML 管理页
- 负责请求校验、响应转换和基础错误映射

### 6.2 agent

职责：

- 使用 `LangGraph` 编排监控运行状态流
- 管理节点输入输出和状态快照
- 不直接依赖具体 MCP Server 或具体 LLM 提供方

固定工作流：

`load_topic -> retrieve_business_context -> expand_queries -> plan_sources -> retrieve_candidates -> fetch_contents -> extract_structured_items -> deduplicate_items -> score_items -> decide_push -> persist_push_records -> evaluate_run`

### 6.3 tools

职责：

- 封装受控工具能力
- 所有工具通过统一 `ToolRegistry` 调用
- 所有工具返回统一 `ToolResponse`

MVP 工具范围：

- `load_topic`
- `keyword_expand`
- `rss_fetch`
- `mock_search`
- `fetch_article_content`
- `extract_article`
- `deduplicate_items`
- `score_candidate`
- `decide_push`
- `record_push`

### 6.4 llm

职责：

- 定义 `BaseLLMClient`
- 实现 `MockLLMClient`
- 为后续真实 OpenAI-compatible provider 预留实现入口

MVP 原则：

- 只允许 `MockLLM` 参与关键词扩展、结构化抽取辅助和评分辅助
- 禁止在未实现真实 provider 时对外宣称“已接模型服务”

### 6.5 storage

职责：

- `PostgreSQL` 作为主题、运行、候选、抽取结果、推送记录、事件、评估结果的事实源
- `Redis` 作为运行锁、短期去重键、短期运行态缓存
- `Repository` 层对数据库细节做统一封装

原则：

- 长期业务结果只认 `PostgreSQL`
- `Redis` 只做辅助状态，不做唯一事实源

### 6.6 rag

职责：

- 管理本地 `JSONL` 业务知识库
- 提供主题词、可信来源、推送规则、历史推送摘要召回

MVP 范围：

- 仅做本地知识文件 + 关键词检索
- 不做向量数据库
- 不做 embedding 检索

### 6.7 scheduler

职责：

- 使用 `APScheduler` 产生监控任务
- 支持手动触发与定时触发
- MVP 先在进程内执行运行闭环

原则：

- `APScheduler` 负责触发，不负责替代完整队列系统
- 第二阶段才引入 `Redis Stream + Worker`

### 6.8 observability

职责：

- 记录运行事件、耗时、错误、降级、评估结果
- 输出事件时间线
- 为后续质量观测后台打基础

## 7. 核心数据流

### 7.1 主题创建

- 用户通过 API 或 HTML 页创建主题
- 主题配置写入 `topics` 表
- 返回 `topic_id`、状态和创建时间

### 7.2 运行触发

- 用户手动触发或 APScheduler 定时触发
- 创建 `monitor_runs` 记录
- 在 `Redis` 中写入运行锁和短期运行态

### 7.3 Agent 执行

- `load_topic` 读取主题配置
- `retrieve_business_context` 从本地知识库召回主题上下文
- `expand_queries` 生成本轮检索词
- `plan_sources` 决定使用 `RSS` 与 `mock_search`
- `retrieve_candidates` 拉取候选池
- `fetch_contents` 进行正文抓取，失败时显式降级为摘要模式
- `extract_structured_items` 输出结构化资讯
- `deduplicate_items` 基于 URL、标题和正文指纹去重
- `score_items` 计算相关性、价值性、新颖性和来源可信度
- `decide_push` 根据阈值和冷却时间给出决策
- `persist_push_records` 落库推送记录和历史
- `evaluate_run` 生成规则评估结果

### 7.4 状态与持久化

- 关键状态快照写入 `monitor_runs`
- 候选池、结构化结果、推送记录、事件、评估结果分别写入对应表
- 所有错误和降级写入 `events` 与错误字段

## 8. API 冻结范围

本轮仅实现以下 API：

- `POST /api/topics`
- `GET /api/topics`
- `GET /api/topics/{topic_id}`
- `POST /api/monitor/{topic_id}/run`
- `GET /api/monitor/runs/{run_id}`
- `GET /api/monitor/runs/{run_id}/candidates`
- `GET /api/pushes`
- `GET /api/topics/{topic_id}/pushes`
- `GET /api/monitor/runs/{run_id}/events`
- `POST /api/eval/run`

不在首轮新增额外接口，避免策略漂移。

## 9. 核心实体冻结范围

### 9.1 topics

字段范围：

- `topic_id`
- `name`
- `description`
- `seed_keywords`
- `trusted_sources`
- `exclude_keywords`
- `push_threshold`
- `cooldown_hours`
- `enabled`
- `schedule_cron`
- `created_at`
- `updated_at`

### 9.2 monitor_runs

字段范围：

- `run_id`
- `topic_id`
- `status`
- `state_snapshot`
- `error_summary`
- `started_at`
- `finished_at`
- `created_at`

### 9.3 candidate_items

字段范围：

- `candidate_id`
- `run_id`
- `topic_id`
- `source_type`
- `source_name`
- `title`
- `url`
- `published_at`
- `raw_summary`
- `fetch_status`
- `created_at`

### 9.4 extracted_items

字段范围：

- `extracted_id`
- `candidate_id`
- `run_id`
- `topic_id`
- `canonical_url`
- `title`
- `source`
- `summary`
- `keywords`
- `entities`
- `content_fingerprint`
- `created_at`

### 9.5 push_records

字段范围：

- `push_id`
- `run_id`
- `topic_id`
- `candidate_id`
- `extracted_id`
- `should_push`
- `score`
- `decision_reason`
- `pushed_at`
- `created_at`

### 9.6 events

字段范围：

- `event_id`
- `run_id`
- `topic_id`
- `event_type`
- `node`
- `message`
- `payload`
- `elapsed_ms`
- `created_at`

### 9.7 eval_results

字段范围：

- `eval_id`
- `run_id`
- `topic_id`
- `retrieved_count`
- `deduped_count`
- `dedup_rate`
- `push_count`
- `duplicate_push_count`
- `tool_success_rate`
- `fetch_success_rate`
- `trace_completeness`
- `suggestions`
- `created_at`

## 10. Agent 状态字段冻结

首轮状态字段必须与指导文档保持一致，不随意改名：

- `run_id`
- `topic_id`
- `topic`
- `seed_keywords`
- `expanded_queries`
- `business_context`
- `source_plan`
- `candidate_items`
- `fetched_contents`
- `extracted_items`
- `deduped_items`
- `scored_items`
- `final_decisions`
- `decision_reasons`
- `push_records`
- `push_history`
- `tool_results`
- `eval_result`
- `events`
- `errors`
- `status`

## 11. HTML 管理页范围

极简 HTML 管理页仅提供以下视图：

1. 主题列表与创建页
2. 运行触发与运行状态页
3. 候选池与推送记录页
4. 事件时间线与评估页

约束：

- 仅使用服务端模板或极简静态页面，不引入复杂前端工程
- 仅服务于 MVP 验证与演示
- 不扩展为第二阶段后台系统

## 12. 失败与降级策略

必须按指导文档显式实现以下策略：

- `RSS` 拉取失败时，记录事件并继续其他来源
- `mock_search` 失败时，记录事件并继续可用来源
- 正文抓取失败时，显式降级为摘要模式
- `MockLLM` 输出异常时，返回结构化错误并终止当前节点
- 数据库写入失败时，运行状态标记失败并记录错误事件
- `Redis` 不可用时，允许降级部分短期状态能力，但不得影响 PostgreSQL 持久化事实

原则：

- 不吞错
- 不静默回退
- 不把失败伪装成成功

## 13. 验收口径

MVP 完成必须满足以下条件：

1. 可以创建真实主题并写入 `PostgreSQL`
2. 可以通过 API 或 HTML 页手动触发一次监控运行
3. 可以从 `RSS + mock_search` 获取真实候选数据
4. 可以进行正文抓取，失败时有明确降级
5. 可以完成结构化抽取、去重、评分与推送决策
6. 可以把候选、事件、推送记录、评估结果真实落库
7. 可以通过 Swagger 和极简 HTML 页查询运行结果
8. 可以在 `MockLLM` 模式下完整跑通，不虚报真实 MCP、浏览器、向量检索或第二阶段能力

## 14. 首轮交付物

首轮交付物应包括：

- 项目目录骨架
- 可运行 `FastAPI` 服务
- `PostgreSQL` 与 `Redis` 配置接入
- `LangGraph` 状态流骨架
- MVP API
- 极简 HTML 管理页
- 本地 `JSONL` RAG 数据
- 基础测试
- README 启动说明

## 15. 当前环境说明

当前 `E:\bgagent2` 目录不是 Git 仓库，因此本设计文档本轮无法提交版本控制。若后续需要遵循文档中的 commit 流程，应先初始化 Git 仓库。
