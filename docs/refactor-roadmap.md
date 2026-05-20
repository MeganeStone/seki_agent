# 阶段性实施计划

本计划用于控制工程化改造节奏。每完成一个阶段，需要确认后再进入下一阶段。

## 阶段 0：文档基线与需求澄清

目标：

- 建立 `docs/` 文档目录。
- 记录当前项目现状。
- 列出需求、架构、部署、安全和验收方面的待确认问题。

产出：

- `docs/README.md`
- `docs/requirements-questions.md`
- `docs/refactor-roadmap.md`

状态：已完成。

## 阶段 1：正式需求文档

目标：

- 根据已确认答案，形成正式需求文档。
- 明确 MVP 范围和后续迭代范围。
- 明确用户角色、核心流程、非功能需求和验收标准。

计划产出：

- `docs/requirements.md`

进入条件：

- 用户确认需求澄清清单中的关键问题。

状态：已完成初稿，等待用户确认。

## 阶段 2：目标架构设计

目标：

- 设计前后端分离架构。
- 设计后端模块边界。
- 设计数据存储、文件存储、向量库、任务队列和模型服务调用方式。
- 设计高并发、高可用演进路径。

初步推荐技术栈：

- 后端：FastAPI。
- 前端：React + Vite + TypeScript。
- 数据库：开发期 SQLite 可保留，生产建议 PostgreSQL。
- 缓存/队列：Redis。
- 异步任务：Celery 或 RQ。
- 向量库：短期 Chroma，后续可迁移 Qdrant。
- 文件存储：开发期本地目录，生产建议 MinIO。
- 测试：pytest、pytest-asyncio、httpx、pytest-mock。
- 代码质量：ruff、mypy、pre-commit。

计划产出：

- `docs/architecture.md`
- `docs/api-design.md`

状态：已完成初稿，等待用户确认。

## 阶段 3：工程骨架落地

目标：

- 新建规范后端目录。
- 引入 FastAPI 应用入口。
- 建立配置、日志、异常、健康检查和基础测试。
- 不迁移复杂业务逻辑，只完成骨架。

计划产出：

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/api/`
- `backend/tests/`
- 基础健康检查接口。

状态：已完成最小后端骨架，已创建后端虚拟环境并通过健康检查测试。

## 阶段 4：模块拆分与迁移

目标：

- 将现有功能按模块迁移。
- 每个模块具备独立测试能力。

当前进展：

- 已重新实现 `auth` 模块骨架。
- 已提供内部账号密码登录接口。
- 已提供当前用户接口。
- 已提供新用户库创建脚本。
- 已通过认证和健康检查测试。
- 已实现 `files` 模块骨架。
- 已提供用户隔离的文件上传、列表、下载、删除接口。
- 已设置首期单文件 600MB 限制。
- 已实现 `diff` 模块骨架。
- 已支持两个 `.tar.gz` 文件的版本差分任务接口。
- 已复用现有 `bin_srcdiff.sh` 和 `lib_srcdiff.sh` 的比较逻辑。
- 已实现 `spi` 模块骨架。
- 已支持 `.log` 文件解析任务接口。
- SPI 解析结果以 Excel 文件形式返回。
- 已实现 `translation` 模块骨架。
- 已支持 `.pptx`、`.xlsx`、`.docx` 翻译任务接口。
- 翻译目标语言由用户必填选择。
- 已实现 `chat/rag` 模块骨架。
- 已支持用户隔离的 conversation 和知识库问答消息接口。
- 真实 RAG 逻辑通过 service 懒加载旧 `rag.py` 和 `vector_db.py`。
- 已新增后端 Dockerfile、Docker Compose 服务、环境变量样例和健康检查。

建议模块：

- `auth`：用户、登录、权限。
- `agents`：LangGraph 编排与会话状态。
- `rag`：知识库问答、检索、重排、答案生成。
- `documents`：文件上传、解析、入库。
- `translation`：文档翻译。
- `spi`：SPI log 解析。
- `storage`：数据库、文件存储、向量库适配。

## 阶段 5：前端应用

目标：

- 新建正式前端应用。
- 对接后端 API。
- 覆盖登录、对话、文件管理、任务进度、知识库管理等页面。

当前进展：

- 已新建 `frontend/` React + Vite + TypeScript 应用。
- 已安装前端依赖并生成 `package-lock.json`。
- 已新增 `VITE_API_BASE_URL` 配置和 `frontend/.env.example`。
- 已实现基础 API client，支持后端健康检查和内部账号登录。
- 已建立轻量页面路由骨架，包含登录、知识库问答、文件管理、文档翻译、SPI log 解析和版本差分比较入口。
- 已对接文件管理页面，支持登录 token 下的文件列表、上传、下载和删除。
- 已对接文档翻译页面，支持选择 workspace 中的 `.pptx`、`.xlsx`、`.docx` 文件，创建翻译任务、查询状态和下载结果。
- 已对接 SPI log 解析页面，支持选择 workspace 中的 `.log` 文件，创建解析任务、查询状态和下载 Excel 结果。
- 已对接版本差分比较页面，支持选择两个 `.tar.gz` 文件，创建差分任务、展示 summary/result_text 和下载结果。
- 已对接知识库问答 / Agent 入口页面，支持创建 conversation、发送 message、展示 answer 和 sources。
- 前端导航已将 Chat 页面明确标记为 `Agent 入口`，该入口通过 Chat API 调用后端 AgentService/AgentRunner。
- 已抽取 `TaskResultPanel` 前端通用组件，translation、SPI、diff 页面共享任务状态、字段、错误、预览和下载动作展示。
- Agent 对话页已支持对结构化任务结果执行后续动作：按 `route + task_id` 查询 translation/SPI/diff 任务状态，并可按 `result_file_id` 下载结果文件。
- 已新增 `frontend` Dockerfile。
- 已更新 `docker-compose.yml`，增加 `frontend` 服务并依赖后端健康检查。
- 已完成旧 `old/src/` Agent 工具链与新后端 tool adapter 的差距梳理，并记录到 `docs/agent-migration-plan.md`。
- 已新增 `FileLookupAgentTool`，通过 `FileService` 查询当前用户 workspace 文件，并将 `file_lookup` 注册到 LangChain/LangGraph 工具列表。
- 已补充 Agent 多步工具链契约测试，覆盖 `file_lookup -> translation`、`file_lookup -> spi`、`file_lookup -> diff` 的 file_id 传递。
- 已新增受控 live Agent 工具选择测试，使用 fake file/translation service 验证真实 LangGraph Agent 是否会先调用 `file_lookup` 再调用 `translation`；默认跳过，仅在显式配置 API key 时运行。
- 根据 live 测试反馈，已修复 LangChain/LangGraph 工具的用户上下文绑定：`owner_username` 不再暴露给 LLM 填写，而是由后端按当前 `AgentRequest` 绑定，避免模型填错用户导致隔离风险。
- live 测试已验证真实 LangGraph Agent 可以完成 `file_lookup -> translation`；已在 `TranslationAgentTool` 增加常见目标语言别名规范化，将 `en/english/英文` 等统一为 `英语`，保持下游任务字段一致。
- 已补充受控 live Agent 工具选择测试，覆盖 `file_lookup -> spi` 和 `file_lookup -> diff`；默认跳过，仅在显式配置 API key 时运行。
- 已新增 `WebSearchAgentTool` 和 `WebSearchService` 抽象，默认使用禁用态 service，不进行外网调用；已注册为可选 LangChain/LangGraph 工具并补充单元测试。
- 已整理 Docker 打包范围：后端镜像只复制 `backend/app`、`backend/scripts`、`backend/legacy`，不再复制旧 `src/` 原型目录；compose 不再挂载 `src/` 和根目录 `parse_spi/`。
- 已新增 `docs/docker-deploy.md`，记录另一台电脑构建、启动、创建用户和访问方式。
- 已完成阶段 6 第一小步：新增 `TaskExecutor` 抽象和默认 `SynchronousTaskExecutor`，translation/SPI/diff 的 `create_task` 已拆为创建任务、提交执行器和 `_run_task` 执行业务三段；当前默认同步执行，API 返回和既有测试保持兼容。
- 已补充任务执行器测试，验证默认同步执行，以及注入延迟执行器时任务可先保持 `pending`，执行后再更新为 `succeeded`。
- 已完成无新依赖的进程内后台线程执行器：`ThreadPoolTaskExecutor` 可通过 `SEKI_TASK_EXECUTOR=thread` 启用，`SEKI_TASK_EXECUTOR_MAX_WORKERS` 控制线程数；FastAPI lifespan 负责创建和关闭执行器。
- 后台线程执行 translation/SPI/diff 时会重新打开数据库连接并重建 service，避免请求级连接关闭后后台任务失效。
- 已更新 `.env.example` 和 `backend/README.md`，记录任务执行器配置。
- 已整理项目根目录：旧原型、旧工作区数据和旧依赖文件已集中移动到 `old/`；根 `.env` 已从新框架 `.env.example` 重新生成，避免 Docker Compose 读取旧框架配置。
- 已修复本地联调登录失败问题：根 `.env` 不能使用 Docker 的 `/app/data/...` 路径裸跑后端，已改为 Windows 项目内 `data/` 绝对路径；`create_user.py` 现在会打印实际写入的数据库路径，便于排查账号写入库和后端读取库不一致的问题。
- 已修复工具联调问题：文件名保留中文；SPI 支持多 log 合并为一个任务/一个 Excel；任务响应返回真实 `result_filename`；后端启动时加载根 `.env` 裸变量，使旧翻译器能读取 `TRANSLATE_API_KEY`；翻译下载名修正为 `原文件名_目标语言.扩展名`。
- 已修复 Excel 翻译覆盖不足：旧翻译器除 `sharedStrings.xml`、drawing、chart 外，已支持 `xl/worksheets/sheet*.xml` 中的 `inlineStr/str` 文本；若没有任何可翻译文本，会让任务失败而不是生成未翻译文件。
- 已修复日语翻译时部分分组失败问题：`translate_text.py` 正确导入 `ToolException`，并且 Excel 分组翻译改为单元级容错，单个文本失败不会让整组失败。

下一步计划：

- 请用户确认是否切换本地 `.env` 为 `SEKI_TASK_EXECUTOR=thread` 并做一次手工联调；若确认，可启动后端和前端，通过页面发起 translation/SPI/diff，观察创建任务后页面轮询查询状态。
- 后续可继续完善任务体验：统一任务历史接口、任务取消/失败重试、任务进度字段更新、前端轮询节流与错误提示。
- 若后台线程 MVP 验证通过，再进入 Redis + Celery/RQ 的生产化队列设计。
- Docker 镜像仍建议用户在本机或另一台电脑执行 `docker compose build && docker compose up -d` 验证。

Agent 主线说明：

- 前端页面不是最终目标，只是 Agent 工程化落地的交互入口和调试台。
- 核心目标仍是将旧 Streamlit/LangGraph Agent 重构为后端可测试、可隔离、可并发的 `agents` 模块，并通过 `chat/rag` API 暴露给前端。
- 后续阶段会重点处理会话状态隔离、工具调用边界、RAG mock 测试、Agent 编排测试和长任务调度。
- 最终保留双入口：用户既可以通过 Agent 对话自动调用工具，也可以通过前端页面手动点击使用同一批工具能力。
- 双入口共享后端 service 层，避免 Agent 工具和前端 API 各自重复实现业务逻辑。

当前 Agent 主线进展：

- 已新增 `AgentService` 后端边界。
- `chat` API 已从直接调用 `RagService` 调整为调用 `AgentService`。
- 当前 `AgentService` 通过可注入 `AgentRunner` 生成回答，默认 runner 仍可委托 RAG，保持前端 Chat API 不变。
- 已补充 `AgentService` 单元测试，覆盖 RAG 委托、消息记录和用户会话隔离。
- 已新增首批 Agent tool adapter：RAG、translation、SPI、diff。
- 已补充 tool adapter 单元测试，验证参数映射、service 调用和返回结构。
- 已新增 `RuleBasedAgentRunner`，用于在接入真实 LangGraph 前验证工具路由和 runner 注入边界。
- 已补充 runner 单元测试，覆盖 RAG、translation、SPI、diff 和禁用知识库分支。
- 已新增 `LangGraphAgentRunner` 最小边界和 runner factory。
- 用户已手动安装 `langgraph`、`langchain`、`langchain-openai`，默认 runner 仍保持 `rule`，可通过 `SEKI_AGENT_RUNNER="langgraph"` 切换。
- 已新增 LangChain tool adapter，可将现有 Agent tool adapter 包装为 `StructuredTool`。
- 已补充 LangChain tool adapter 单元测试。
- 已新增 LangGraph graph factory，使用 `ChatOpenAI`、`StructuredTool` 和 `create_agent` 创建 TBOX Agent graph。
- 已补充 graph factory 单元测试，使用 fake model/fake create_agent，不调用真实 LLM。
- 已增强 LangChain tool metadata，约束 Agent 不编造文件 ID。
- 已新增受控 live Agent 测试，默认跳过，仅在显式配置 `SEKI_RUN_LIVE_AGENT_TESTS=true` 和 API key 时调用真实模型。
- 已修复 LangGraph checkpointer 配置，graph invoke 会传入 `thread_id=owner_username:conversation_id` 和 `checkpoint_ns=seki-agent`。
- 已修复 LangGraph 返回结构解析，兼容 `{"messages": [...]}` 返回并提取最后一条消息内容。
- 已将 translation、SPI、diff service 注入 `AgentService` 默认 runner，Agent 对话入口可以复用前端手动入口背后的同一批 service。
- 已补充 `AgentService` 工具路由单元测试。
- 已扩展 Chat API 响应，保留 Agent runner 的 `route` 和 `data`，让工具调用结果可被前端展示和后续下载/任务查询复用。
- 已更新前端 Agent 对话页，展示工具路由、任务 ID、状态、结果文件 ID 和错误信息。

Live Agent 测试运行方式：

```powershell
$env:SEKI_RUN_LIVE_AGENT_TESTS='true'
$env:SEKI_RAG_API_KEY='你的 key'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py -m live
```

Live 测试注意：

- 不要把 API key 写入仓库文件。
- `test_live_langgraph_agent_uses_file_lookup_before_translation` 使用 fake service，不会真的翻译文件或写业务数据，但会访问真实模型服务。
- 当前自动化环境可能限制外网访问，无法放行时需要用户在本机终端手动运行。
- 如果该测试曾出现 `file_service.calls == ["user"]` 之类错误，说明模型尝试自行填写用户名；当前实现已改为后端绑定用户名，重新运行即可验证。

Agent 测试原则：

- service 层测试业务规则、持久化和文件隔离。
- tool adapter 测试参数映射和结果格式，使用 fake service，不访问数据库、文件系统或外部 API。
- LangGraph/Agent 编排测试使用 mock LLM 或 fake runner，验证工具选择、会话隔离和错误处理。

## 阶段 6：异步任务与并发优化

目标：

- 将耗时任务迁移到后台任务队列。
- 引入任务状态查询、进度展示、失败重试。
- 优化 Agent 会话隔离和并发安全。

当前进展：

- 已新增后端任务执行器边界：`backend/app/services/task_executor.py`。
- 已提供默认 `SynchronousTaskExecutor`，不引入新依赖，不改变当前同步执行体验。
- translation/SPI/diff service 已改为通过执行器提交任务，业务执行逻辑收敛到各自 `_run_task` 方法。
- 已新增 `backend/tests/test_task_executor.py`，覆盖执行器契约和延迟执行场景。
- 已新增 `ThreadPoolTaskExecutor`，支持本机进程内后台线程执行；通过配置 `SEKI_TASK_EXECUTOR=thread` 启用。
- FastAPI lifespan 会创建执行器并在应用关闭时执行 `shutdown(wait=True)`。
- translation/SPI/diff 后台执行路径会在线程内重新打开数据库连接，避免请求连接生命周期问题。
- 已验证命令：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_task_executor.py backend\tests\test_translation.py backend\tests\test_spi.py backend\tests\test_diff.py backend\tests\test_agent_tools.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_health.py
```

验证结果：37 passed。

## 阶段 7：生产化部署与高可用

目标：

- 完善 Docker Compose。
- 引入 PostgreSQL、Redis、对象存储、向量库服务。
- 增加健康检查、日志、监控、备份和恢复方案。
- 形成生产部署文档。
