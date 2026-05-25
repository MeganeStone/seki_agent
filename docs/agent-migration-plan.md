# Agent 迁移计划

本文档记录旧 Streamlit/LangGraph Agent 向新 FastAPI 工程结构迁移的边界和顺序。

## 1. 双入口目标

最终保留两种入口：

- Agent 对话入口：用户通过自然语言让 Agent 自动判断并调用 RAG、翻译、SPI 解析、版本差分等工具。
- 前端手动入口：用户也可以直接通过页面按钮使用同一批工具能力。

两种入口共享后端 service 层，避免重复实现业务逻辑。

## 2. 旧代码现状

主要文件：

- `old/src/multi_agent.py`：顶层 LangGraph，多 Agent 路由到主 Agent 和代码 Agent。
- `old/src/tbox_doc_agent.py`：主业务 Agent，集成 RAG、翻译、web search、SPI 解析、版本比较和转交代码助手。
- `old/src/tools.py`：旧 Agent 工具定义，直接操作 workspace、本地脚本和旧模块。
- `old/src/rag.py`、`old/src/vector_db.py`：RAG 链、向量库加载、文档入库和检索。

关键风险：

- `multi_agent.py` 使用闭包变量 `main_context` / `code_context` 保存上下文，不适合多用户并发。
- 旧工具直接访问本地路径和旧模块，缺少统一的用户隔离、任务记录和错误标准化。
- `tbox_doc_agent.py` 依赖 Streamlit spinner 初始化向量库，后端服务环境中不应依赖 UI。
- 旧 Agent 工具和新后端 `translation/spi/diff/files/rag` service 存在重复能力，需要统一收敛。

## 3. 新后端现状

已具备：

- `auth`：内部账号密码登录。
- `files`：用户隔离 workspace 文件。
- `translation`：任务化文档翻译。
- `spi`：任务化 SPI log 解析。
- `diff`：任务化版本差分比较。
- `chat/rag`：conversation、message 保存和 RAG 问答入口。
- `agent_service`：已新增用户侧 Agent 入口边界，当前委托 `RagService` 生成回答，后续可在不改变 Chat API 的前提下接入 LangGraph 编排。

当前 `chat/rag` 仍是最小 RAG 问答，不是完整 Agent 编排。

## 4. 迁移原则

- Agent 会话状态按 `owner_username + conversation_id` 隔离。
- 主 Agent 和 code agent 的上下文必须隔离，新的持久化或 checkpointer key 至少包含 `owner_username + conversation_id + agent_name`，不能继续使用旧 `multi_agent.py` 中的进程级闭包列表。
- `code_agent` 是根据任务需要由主 Agent 切换的上下文隔离子 Agent，不提供前端独立入口。
- `web_search` 是 Agent 专用联网工具，不需要前端页面；默认应可关闭，并保留超时、结果裁剪和错误映射。
- RAG 知识库源文件由本地维护者更新或删除，普通用户不能通过前端上传文件到 RAG 系统。
- Agent 工具层调用后端 service，不直接重复实现文件、翻译、SPI、diff 业务逻辑。
- 长任务工具返回 task 信息，由前端或 Agent 后续查询状态。
- 长任务必须支持用户手动终止；首期采用协作式取消，后续生产化 worker 再增强为进程级终止。
- RAG 与外部 LLM 必须支持 mock 测试，避免单元测试依赖真实 API。
- 工具错误统一映射为用户可理解的消息，不泄露内部路径、token 或 API key。
- 每个 Agent tool adapter 必须能脱离 FastAPI、数据库和真实文件系统独立单元测试。
- service 层负责业务规则和持久化，tool adapter 只负责参数映射、调用 service 和整理返回给 Agent 的文本/结构化数据。
- LangSmith 可继续作为联调和真实 Agent 运行追踪工具，但单元测试和 CI 不能依赖 LangSmith 或真实外部 API。

## 5. 建议迁移顺序

1. 将现有 `chat/rag` 前端页面作为 Agent 主入口。
2. 在后端新增 `services/agent_service.py`，封装 Agent 调用边界。
3. 新增 `services/agent_tools.py` 或 `agents/tools.py`，把 `files/translation/spi/diff/rag` service 包装成 Agent 工具。
4. 将旧 `tbox_doc_agent.py` 的 system prompt 和工具选择规则迁移到后端 Agent 工厂。
5. 替换旧闭包上下文，使用 repository 保存 conversation/messages，必要时再引入 LangGraph checkpointer 持久化。
6. 增加 Agent service 单元测试：mock LLM、mock tools、验证工具选择和会话隔离。
7. 再评估是否迁移 `code_agent`，以及它是否应允许操作本地文件。

## 6. 下一步落点

已完成第一步后端 Agent 边界：

- 新增 `AgentService` 接口。
- 先让 `AgentService.ask(...)` 复用当前 `RagService` 行为，保持 API 不变。
- 补充 `AgentService` 单元测试，确认消息记录、RAG 委托和用户隔离。
- 前端 Chat 页面不需要感知背后是 RAG 还是 Agent。
- 新增首批 Agent tool adapter：RAG、translation、SPI、diff。
- 已补充 tool adapter 单元测试，使用 fake service 验证参数映射和返回结构，不依赖真实 LLM、数据库和文件系统。
- 新增 `AgentRunner` 边界和 `RuleBasedAgentRunner`。
- `AgentService` 已改为通过 runner 生成回答，runner 可注入，便于后续替换为 LangGraph runner。
- 已补充 runner 单元测试，验证 RAG、translation、SPI、diff 和禁用知识库分支。
- 新增 `LangGraphAgentRunner` 最小边界，支持注入 graph factory，在测试中不依赖真实 LangGraph 或 LLM。
- 新增 runner factory，默认缺少 LangGraph 依赖时降级到 `RuleBasedAgentRunner`。
- 用户已手动安装 `langgraph==1.2.0`、`langchain==1.3.1`、`langchain-openai==1.2.1`，同时 `langchain-core` 升级为 `1.4.0`。
- 已新增 `langchain_tool_adapter.py`，可将现有 Python tool adapter 包装为 `langchain_core.tools.StructuredTool`。
- 已补充 LangChain tool adapter 单元测试，验证工具名称、参数映射和调用结果。
- 已新增 `langgraph_agent_factory.py`，可使用 `ChatOpenAI`、`StructuredTool` 和 `create_agent` 创建 TBOX Agent graph。
- 已补充 graph factory 单元测试，通过 fake `create_agent`/fake model 验证工具注入，不调用真实模型。
- 已增强 LangChain tool metadata，明确要求不要编造 `file_id` / 文件 ID，必须来自用户已上传文件或前端选择。
- 已新增受控 live Agent 测试 `test_live_langgraph_agent.py`，默认跳过，仅在 `SEKI_RUN_LIVE_AGENT_TESTS=true` 且配置 API key 时运行。
- 已修复 LangGraph checkpointer 调用：`LangGraphAgentRunner.run(...)` 会传入 `configurable.thread_id` 和 `checkpoint_ns`，其中 `thread_id` 使用 `owner_username:conversation_id:agent_name`，保证用户会话与子 Agent 上下文隔离。
- 已修复 LangGraph 返回解析：`create_agent` 返回 `messages` 时，runner 会提取最后一条 message 的 content 作为 answer。
- `AgentService` 默认 runner 已注入 translation、SPI、diff service；Agent 工具和前端按钮共用同一套 service 能力。
- 已补充 `AgentService` 层工具路由测试，覆盖 translation、SPI、diff 的显式调用。
- 已新增 `HandoffAgentRunner` 和 `CodeAgentUnavailableRunner`，用于建立主 Agent/code agent 的隔离边界；默认不再通过关键词硬编码判断是否进入 `code_agent`。
- 已在 `AgentRequest` 增加 `agent_name`，并将 LangGraph checkpointer `thread_id` 调整为 `owner_username:conversation_id:agent_name`，为主 Agent/code agent 上下文隔离打基础。
- Chat/翻译入口当前已收敛为后端环境变量配置 API key；前端不再传入临时 key，缺 key 时提示维护者配置后端环境变量。
- 已新增 `transfer_to_code_agent` handoff 工具和父级 multi-agent graph：主 Agent 可通过 LangGraph `Command` 交接到 `code_agent` 占位节点，恢复旧框架“Agent 自己判断是否交接”的方向。

下一步建议：

- 增加真实 LangGraph runner 的工具选择评估用例，先用 fake tool/fake data 验证模型是否按 prompt 正确选择工具。
- 继续迁移旧 `code_agent`：真实 LangGraph handoff 骨架已落地，已新增 `docs/code-agent-design.md`，并已实现和接入 `CodeExecutionService`：`list_dir/read_text_file/write_text_file/run_python_script`，默认禁用任意 shell。默认 allowed roots 包含当前用户 workspace、项目根和共享 skills 目录，为后续 skills 热插拔预留；默认写入限制在 `data/workspace/{username}`。

## 7. 旧 Agent 与新后端差距清单

### 7.1 已迁移或已替代能力

| 旧能力 | 旧入口 | 新后端状态 | 说明 |
| --- | --- | --- | --- |
| RAG 问答 | `tbox_doc_agent.py` + `tools.create_rag_qa_tool` | 已接入 `RagAgentTool` | 新实现通过 `RagService` 懒加载旧 RAG 逻辑，并支持 mock answerer 测试。 |
| 文档翻译 | `tools.create_translate_file_tool`，按文件名/路径调用 | 已接入 `TranslationAgentTool` | 新实现改为 `file_id + owner_username`，由 `TranslationService` 负责用户隔离、任务记录和结果文件。 |
| SPI 解析 | `tools.create_parse_spi_tool`，按 workspace 相对路径调用 | 已接入 `SpiAgentTool` | 新实现改为上传文件 `file_id`，结果以任务和文件形式返回。 |
| 版本差分 | `tools.create_compare_versions_tool`，按两个文件名调用 | 已接入 `DiffAgentTool` | 新实现复用脚本能力，但由 `DiffService` 管理任务、工作目录和结果。 |
| 文件查找 | 旧工具按文件名直接访问 workspace | 已接入 `FileLookupAgentTool` | 新实现通过 `FileService.list_files(owner_username)` 查询当前用户文件，并返回可给其他工具使用的 `file_id`。 |
| 联网搜索抽象 | `tools.create_web_search_tool` | 已接入 `WebSearchAgentTool` 抽象和默认禁用 service | 新实现先落 service/tool 协议与单元测试，默认不外连；真实 provider 后续单独接入。 |
| LangGraph runner | `multi_agent.py` / `tbox_doc_agent.py` | 已有最小 `LangGraphAgentRunner` | 新实现通过 `owner_username:conversation_id:agent_name` 作为 `thread_id`，避免旧闭包上下文的多用户串话和主/code agent 上下文混用风险。 |

### 7.2 尚未迁移能力

| 旧能力 | 旧入口 | 当前缺口 | 迁移建议 |
| --- | --- | --- | --- |
| 联网搜索真实 provider | `tools.create_web_search_tool` | 已有 `WebSearchService` 协议和默认禁用实现，但尚未接真实 provider、缓存、配额和审计 | 后续接入真实 provider 时保持默认关闭，补超时、结果裁剪、错误映射和配置开关。 |
| 代码助手 | `code_agent.py` + `multi_agent.py` transfer 工具 | 已有 `HandoffAgentRunner`、`transfer_to_code_agent`/`transfer_to_main_agent`、父级 multi-agent graph、`CodeExecutionService`、code_agent LangChain 工具；已支持受限 Python 脚本执行、直接删除本次运行创建的内容、命令白名单；未知命令和既有文件删除会进入确认；真实任意 shell 和确认执行流程尚未开放 | 下一步补 pending operation 后端 API/UI，并评估将命令白名单配置化；shell 不直接给任意字符串。 |
| 多 Agent 交接 | `transfer_to_code_agent` / `transfer_to_main_agent` | 主 Agent 到 code_agent 的 LangGraph handoff 骨架已接入；`thread_id` 已包含 `agent_name`；code_agent 到主 Agent 的回交和真实 code graph 尚未接入 | 继续使用 `owner_username + conversation_id + agent_name` 隔离上下文；后续在 code_agent graph 中补 `transfer_to_main_agent`。 |
| 长上下文摘要 | `SummarizationMiddleware` | 新后端暂未接入摘要中间件 | 等 conversation 历史查询和持久化策略明确后再引入；需要 mock LLM 测试。 |
| 文件名自然语言选择 | 旧工具按 `file_name` 从 workspace 找文件 | 已有 `FileLookupAgentTool`，但仍需真实 LangGraph 工具选择评估 | 用 fake data/live smoke 验证 Agent 是否会先查文件再调用 translation/SPI/diff。 |

### 7.3 下一批推荐迁移顺序

1. 补 Agent 工具选择评估测试：使用 fake graph/fake model 验证翻译、SPI、diff、RAG、file_lookup 场景的参数和返回结构。
2. 设计“前端选中文件上下文”是否要随 Chat message 传给 Agent，降低模型查错文件的概率。
3. 接入真实 `web_search` provider：保持默认关闭，先补配置开关、超时、结果裁剪、错误映射和单元测试，再调用真实供应商；不做前端页面。
4. 继续迁移 `code_agent`：下一步补 pending operation 后端 API/UI，承接既有文件删除和未知命令确认；后续再评估 LangGraph interrupt 或 HITL 中间件。
