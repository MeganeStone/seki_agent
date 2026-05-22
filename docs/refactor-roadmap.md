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
- 已修复前端任务状态面板切换页面后消失的问题：translation/SPI/diff 页面会把最近一次任务缓存到 `localStorage`，页面重新挂载时恢复 `TaskResultPanel` 并刷新后端状态；本次改动已通过 `npm run build` 和 `npm run lint`。
- 已新增统一任务只读接口：`GET /api/v1/tasks` 聚合当前用户 translation/SPI/diff 最近任务，`GET /api/v1/tasks/{task_id}` 按统一格式查询单个任务；已补充 `backend/tests/test_tasks.py` 覆盖任务列表、单任务查询、limit 和用户隔离。
- 已新增前端 `任务历史` 页面和导航入口，调用统一任务接口展示最近任务；当前为只读列表，显示任务类型、状态、任务 ID、结果文件 ID、更新时间和错误信息。本次改动已通过 `backend/tests/test_tasks.py`、`npm run build` 和 `npm run lint`。
- 已确认主线边界：`web_search` 仅作为 Agent 联网工具，不做前端页面；`code_agent` 是按任务切换的上下文隔离子 Agent，不做独立入口；RAG 知识库源文件只允许本地维护者更新或删除；用户之间的文件、任务、会话必须隔离。
- 已补充 `docs/architecture.md` 和 `docs/agent-migration-plan.md`，明确“工程化、可测试、可替换”的具体落地含义，以及 LangSmith 作为真实链路追踪而非单元测试前提。
- 已新增长任务协作式取消：统一任务接口支持 `POST /api/v1/tasks/{task_id}/cancel`，translation/SPI/diff 在开始和写入结果前检查 `cancelled` 状态；前端任务历史页新增“终止”按钮。本次改动已通过 26 个受影响后端测试、`npm run build` 和 `npm run lint`。
- 已完成 `code_agent` handoff 骨架修正：`HandoffAgentRunner` 仅保留主 Agent/code agent 上下文隔离边界，默认不再通过关键词硬编码猜测代码类请求；真实切换后续应通过 LangGraph handoff tool/子图由 Agent 自主调用。`AgentRequest.agent_name` 和 LangGraph `thread_id=owner_username:conversation_id:agent_name` 已打通上下文隔离。
- 已新增 Chat/翻译任务的临时 API key 输入契约：后端始终优先使用环境变量（如 `SEKI_RAG_API_KEY`、`TRANSLATE_API_KEY`），环境未配置时才使用前端请求携带的临时 key；两者都没有时返回用户可理解的缺 key 提示，且不把 key 写入对话消息或任务记录。
- 已完成真实 LangGraph handoff 骨架：新增 `transfer_to_code_agent` 工具，主 Agent 可通过工具返回 `Command(goto="code_agent")`；新增父级 `multi_agent_graph_factory`，组合 main agent 节点和 `code_agent` 占位节点，并捕获子图 `Command.PARENT` 交接。当前 code_agent 仍只返回“能力迁移中”，不开放真实文件读写或命令执行。
- 已新增 `docs/code-agent-design.md`，重新设计 code agent 的安全执行模型：通过 `CodeExecutionService`、路径策略、命令策略、审计记录和分阶段放权替代旧版直接注册任意 shell/读写/删除工具的方式。
- 已完成 `CodeExecutionService` 阶段 A：新增受限 `list_dir/read_text_file/write_text_file` service，默认不开放删除和任意 shell；包含允许根目录校验、路径越界拒绝、符号链接逃逸拒绝、敏感文件拒绝、读写大小限制、覆盖保护和内存审计记录。
- 已将 `CodeExecutionService` 阶段 A 接入 code_agent：新增 code agent LangChain tool adapter 和 `code_agent_factory`，注册 `code_list_dir`、`code_read_text_file`、`code_write_text_file`、`transfer_to_main_agent`；LangGraph 父图现在可运行真实 code agent graph，但仍不开放 shell 和删除。
- 已将共享 skills 目录纳入 code agent allowed roots 设计：默认 allowed roots 为项目根目录、workspace 和 `skills_dir`，后续 skills 热插拔目录不受单用户 workspace 限制。
- 已新增受限 `run_python_script` 能力和 `code_run_python_script` 工具：只能运行允许目录内已存在的 `.py` 文件，使用当前后端 Python，支持参数列表、超时、输出裁剪和审计；仍不开放任意 shell。
- 已新增确认式删除的第一阶段：`code_create_dir` 可创建目录并标记为 code agent 本次运行创建；`code_delete_path` 可直接删除 code agent 本次运行创建的文件/目录，其他既有内容返回 `requires_confirmation`，等待后续用户确认 API/UI。
- 已新增命令混合策略：不采用纯黑名单，改为“白名单直接执行、明确黑名单拒绝、其他未知命令进入用户确认”。`code_run_allowed_command` 当前允许 `git status/diff`、`pytest`、`python -m pytest`、`npm run lint/build`，并拒绝危险命令和 shell 控制符。
- 已记录人机交互确认策略：当前本地 LangChain/LangGraph 版本未发现可直接稳定接入的 `HumanInTheLoopMiddleware`；短期先做后端 pending operation + 前端确认 UI，后续再评估 LangGraph interrupt。

下一步计划：

- 下一步继续 Agent 主线：补用户确认 API/UI，让既有文件删除和后续高风险命令可以由用户显式批准；同时评估是否把允许命令前缀做成配置项。
- `web_search` 后续只接 Agent provider，不做前端入口；接入时保持默认关闭，补配置开关、超时、结果裁剪、错误映射和测试。
- RAG 后续重点是维护者本地更新流程、RAG service 边界和 mock 测试，不提供普通用户上传入口。
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
- 用户已手动安装 `langgraph`、`langchain`、`langchain-openai`；默认运行时已收敛为 LangGraph runner，不再通过 `SEKI_AGENT_RUNNER` 在 rule/graph 间切换。
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
- 已新增 `HandoffAgentRunner`，在不提供 code_agent 独立前端入口的前提下，为主 Agent/code agent 切换建立后端 runner 边界；该 runner 默认不再根据用户文本关键词决定 handoff，真实切换后续交给 Agent 工具/子图。
- `LangGraphAgentRunner` 已使用 `owner_username:conversation_id:agent_name` 作为 checkpointer `thread_id`，避免主 Agent 和 code agent 共用上下文。
- Chat API 和翻译 API 已支持可选临时 API key。优先级为：环境配置 key > 前端临时 key > 缺 key 提示。
- LangGraph runner 现在通过父级 multi-agent graph 运行 main agent 和 code_agent 占位节点；`transfer_to_code_agent` 工具可触发到 code_agent 边界的真实图内交接。
- 已新增 code agent 安全执行设计文档，明确首期不开放 `execute_shell(command: str)` 和 `delete_file`，而是先做受限文件能力，再逐步增加 Python 脚本执行、命令白名单、确认流程和审计 UI。
- `CodeExecutionService` 阶段 A 已落地并接入 LangGraph code_agent 工具；当前 code_agent 能列目录、读小文本、写小文本，但不能执行 shell 或删除文件。
- code_agent 已能通过 `code_run_python_script` 运行允许目录内的 Python 脚本；共享 skills 目录已作为默认允许根之一，为后续 skills 热插拔预留。
- code_agent 已能清理自己本次运行创建的文件/目录；删除其他既有内容会返回 `requires_confirmation`，当前还没有确认 API/UI。
- code_agent 已能执行白名单命令；当前仍不开放任意 shell 字符串。

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

## Code Agent Pending Operation 进展

已完成后端 MVP：

- `code_pending_operations` 持久化表。
- 待确认操作查询、详情、确认、取消 API。
- `AgentService` 在 runner 返回 `requires_confirmation` 时自动创建 pending operation。
- 用户确认后可执行既有文件/目录删除。
- 未知命令先能进入 pending，但确认后仍不真实执行，等待下一步设计命令确认执行策略。
- 前端 Agent 入口已展示 pending operation，并支持确认执行、取消和刷新待确认。
- code agent 工具调用当场创建 pending operation，降低真实 LangGraph 最终回答丢失结构化 `requires_confirmation` 的风险。
- code agent 命令策略已支持配置化直接执行前缀和确认后执行前缀。

下一步候选：

- 继续扩大工程化主线：引入更正式的任务/事件模型，为 Redis/Celery/RQ 或其他消息队列落地做接口准备。
- 设计 code agent 的持久审计表，把当前内存审计扩展到 DB，支持后续审计 UI 和异常追踪。
- 评估向量数据库生产化迁移路径：短期保留当前 legacy 向量库，文档化 Qdrant/Redis/对象存储的替换边界。

## Agent 入口可测性修正

已完成：

- 新增普通聊天模型 fallback：关闭知识库时不再返回占位提示，而是调用普通聊天模型。
- 普通聊天复用现有模型配置和 API key 优先级。
- 前端 Agent 入口提示已更新，方便用户直接测试普通聊天。
- 已移除运行时 rule/graph 切换和关键词 handoff 配置；默认由 LangGraph Agent 通过 handoff tool 自主切换，`RuleBasedAgentRunner` 只保留为测试构件。
- 新增对话短期记忆：`AgentService` 会读取当前 conversation 最近消息并传入 runner，`ChatModelService` 和 `LangGraphAgentRunner` 会携带最近 20 条 user/assistant 历史。
- 旧 Agent 身份设定已在 `TBOX_AGENT_SYSTEM_PROMPT` 中补齐并对齐新工具契约：SIS/本田/TSU/seki 开发者身份、普通聊天职责、普通问题不乱用工具、翻译默认日语等。
- 新增 Chat SSE 接口和前端流式展示：`/messages/stream` 输出 delta/final 事件，前端 Agent 页优先增量渲染 assistant 回复，并保留旧接口作为兼容兜底。
- 接回火山/Feedcoop 兼容联网搜索 provider：配置环境 key 后启用，或由前端 Agent 页传入本次请求临时火山搜索 key；不再需要 `SEKI_WEB_SEARCH_PROVIDER` 开关。
- 前端 Agent 页已拆分千问 API key 与火山搜索 API key；临时 key 不写入对话。
- 前端 Agent 聊天框已改为内部滚动，避免长对话拉长整个页面。
- LangSmith 追踪建议使用 LangChain/LangGraph 原生环境变量接入，当前无需自定义 trace wrapper。

当前限制：

- SSE 已改善前端流式体验，但仍是 runner 完成后再分片输出最终 answer；真实 token 级流式需下一步扩展 runner stream 协议和 LangGraph/LLM 原生 streaming。
- web_search 已有旧 provider 兼容实现，但还没有做配额、缓存、审计和 provider 抽象管理 UI；后续生产化时继续补。
