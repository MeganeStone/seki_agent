# 当前上下文摘要

本文用于在长对话压缩后快速恢复项目状态。

## 项目目标

将旧 `old/src/` 下基于 Streamlit/LangGraph/LangChain 的公司业务 Agent，重构为工程化前后端分离系统：

- 后端：FastAPI 模块化单体。
- 前端：React + Vite + TypeScript。
- 保留双入口：
  - 用户可通过 Agent 对话自动调用工具。
  - 用户也可通过前端页面手动点击使用工具。
- 两种入口共享后端 service 层，避免重复业务逻辑。
- 各模块尽量解耦，可独立单元测试。

## 已完成后端模块

- `auth`：内部账号密码登录、当前用户识别。
- `files`：用户隔离 workspace 文件上传、列表、下载、删除。
- `translation`：`.pptx/.xlsx/.docx` 翻译任务。
- `spi`：`.log` 解析任务，结果 Excel。
- `diff`：两个 `.tar.gz` 版本包差分任务。
- `chat`：conversation/message API。
- `rag`：当前最小 RAG 回答能力，懒加载新框架收敛后的 `backend/legacy/rag.py`、`backend/legacy/vector_db.py`。
- `agent_service`：Chat API 背后的 Agent 入口边界。
- `agent_tools`：RAG、translation、SPI、diff 的 tool adapter。
- `agent_runner`：`AgentRunner` 协议、测试用 `RuleBasedAgentRunner` 和 handoff 边界。
- `langgraph_agent_runner`：默认运行时 LangGraph runner 边界，支持 fake graph 测试。

## 已完成前端页面

- 登录/健康检查。
- 文件管理。
- 文档翻译。
- SPI log 解析。
- 版本差分比较。
- 任务历史：通过统一任务接口查看 translation/SPI/diff 最近任务。
- Agent 入口：通过 Chat API 调用后端 AgentService/AgentRunner，前端导航已明确显示为 `Agent 入口`。
- `TaskResultPanel` 通用任务结果组件，已被 translation、SPI、diff 页面复用。
- Agent 对话页已支持按 `route + task_id` 查询 translation/SPI/diff 任务状态，并可按 `result_file_id` 下载工具结果文件。

## 关键设计

- `Chat API -> AgentService -> AgentRunner -> Agent tool adapter -> backend service`
- Agent tool adapter 只做参数映射、调用 service、整理返回；不做业务逻辑。
- service 层负责业务规则、持久化、文件隔离。
- 已确认用户之间的文件、任务、conversation/message 必须隔离；跨用户查询、下载、取消任务都必须拒绝。
- `web_search` 是 Agent 专用联网工具，不做前端页面；默认可以保持关闭，后续接真实 provider 时补配置、超时、结果裁剪和错误映射。
- `code_agent` 的定位是主 Agent 按任务需要切换的上下文隔离子 Agent，不提供单独前端入口；新实现不能复用旧 `multi_agent.py` 的进程级闭包上下文。
- RAG 知识库源文件只能由本地维护者更新或删除，普通用户不能通过前端上传到 RAG 系统。
- “工程化、可测试、可替换”的具体含义已记录到 `docs/architecture.md`：边界收敛到 router/service/repository/tool adapter/runner，测试使用 fake service/fake LLM/fake graph，runner/web search/task executor/RAG answerer 都可以替换；LangSmith 保留为真实链路追踪工具，但不作为单元测试前提。
- 长任务工具返回 task/result_file_id，前端或 Agent 可查询/下载。
- 旧 `old/src/multi_agent.py` 的闭包上下文不适合多用户并发，后续必须替换为 `owner_username + conversation_id` 隔离。
- `AgentService` 默认 runner 已注入 RAG、translation、SPI、diff service；Agent 对话入口和前端手动入口共享这些 service。
- Chat API 响应已保留 Agent runner 的 `route` 和 `data` 字段。
- 前端 Agent 对话页已展示结构化工具结果，包括工具路由、任务 ID、状态、结果文件 ID 和错误信息；切换页面后会恢复最近一次 conversation 并从后端拉取历史消息继续对话。
- 已完成旧 `old/src/` Agent 工具链差距梳理：RAG/translation/SPI/diff 已迁移到新后端 service/tool adapter；`web_search` 已有默认禁用抽象；`code_agent` 已有 handoff 骨架但真实代码执行尚未开放；多 Agent 真实 LangGraph 子图交接、长上下文摘要和更强的文件名到 `file_id` 解析仍待设计。
- 已新增 `FileLookupAgentTool`，让 LangGraph Agent 能按当前用户 workspace 文件名/后缀查找文件 ID，降低用户手动输入 `file_id` 的门槛。
- 已补充 Agent 多步工具链契约测试，覆盖 `file_lookup -> translation`、`file_lookup -> spi`、`file_lookup -> diff` 的 file_id 传递。
- 已新增 `HandoffAgentRunner` 和 `CodeAgentUnavailableRunner`，用于建立主 Agent/code agent 上下文隔离边界；默认不再根据关键词硬编码猜测是否切换到 `code_agent`。真实切换后续要通过 LangGraph handoff tool/子图由 Agent 自主调用；当前仍不开放真实代码文件操作或命令执行。
- `AgentRequest` 已新增 `agent_name`，默认 `main_agent`；`LangGraphAgentRunner` 的 `thread_id` 已从 `owner_username:conversation_id` 扩展为 `owner_username:conversation_id:agent_name`，为主 Agent/code agent 上下文隔离打基础。
- API key 已收敛为后端环境变量配置，前端 Agent 和翻译页面不再提供临时 key 输入；Chat API 请求体也不再暴露 `api_key` / `web_search_api_key` 字段。
- 已新增 `agent_handoff_tools.py` 和 `multi_agent_graph_factory.py`：真实 LangGraph runner 会创建父级 multi-agent graph，主 Agent 可通过 `transfer_to_code_agent` 工具返回 `Command(goto="code_agent")`，父图接住后进入 `code_agent` 占位节点。当前 code_agent 仍只返回不可用提示。
- 已新增 `docs/code-agent-design.md`：重新设计 code agent 为受限本地执行助手，首期通过 `CodeExecutionService` 只开放 `list_dir/read_text_file/write_text_file`；`delete_file` 和任意 `execute_shell(command)` 默认不开放，后续通过命令白名单、用户确认和审计逐步放权。
- 已实现 `backend/app/services/code_execution_service.py` 阶段 A，并新增 `backend/tests/test_code_execution_service.py`。当前支持列目录、读 UTF-8 小文本、写 UTF-8 文本；默认拒绝路径越界、符号链接逃逸、敏感文件、超大读写和未显式覆盖已有文件。当前还没有挂到 LangGraph code_agent 工具。
- 已新增 `backend/app/services/code_agent_tools.py`、`backend/app/services/code_langchain_tool_adapter.py`、`backend/app/services/code_agent_factory.py`，并把 `code_list_dir`、`code_read_text_file`、`code_write_text_file`、`transfer_to_main_agent` 接入真实 code_agent graph。默认 runner 会创建 main agent graph + code agent graph。
- Shell 和删除最终目标是开放，但后续必须通过受限 Python 脚本执行、命令白名单、审计和用户确认流程逐步放权，不直接恢复旧版任意 `execute_shell(command)`。
- `CodeExecutionService` 默认 allowed roots 已包含当前用户 workspace、项目根目录和共享 `skills_dir`；skills 是所有用户通用能力，不限制在单用户 workspace 内。code agent 默认可写工作目录为 `data/workspace/{username}`，项目根和 skills 用于读取/执行，不作为默认写入位置。
- 已新增 `run_python_script` 和 `code_run_python_script`：只能运行允许目录内已存在的 `.py` 文件，使用当前后端 Python，支持 `script_args`、超时、stdout/stderr 裁剪和审计；仍不开放任意 shell 和删除。
- 已新增 `create_dir/delete_path` 和 `code_create_dir/code_delete_path`：code agent 本次运行创建的文件/目录可直接删除；其他既有内容返回 `requires_confirmation`，当前尚未实现用户确认 API/UI。
- 已新增 `CommandPolicy`、`run_allowed_command` 和 `code_run_allowed_command`。策略采用“白名单直接执行、明确黑名单拒绝、其他未知命令进入用户确认”，不采用纯黑名单；当前允许 `git status/diff`、`pytest`、`python -m pytest`、`npm run lint/build`，拒绝危险命令和 shell 控制符。仍不开放任意 `execute_shell(command)`。
- 关于人机交互：当前本地 LangChain/LangGraph 版本未发现可直接稳定接入的 `HumanInTheLoopMiddleware`；短期建议先实现后端 pending operation + 前端确认 UI，后续再评估 LangGraph interrupt。
- 已新增受控 live Agent 工具选择测试，使用 fake file/translation service 验证真实 LangGraph Agent 是否会先调用 `file_lookup` 再调用 `translation`；默认跳过，仅显式配置 API key 时运行。
- 已根据 live 测试反馈修复工具用户上下文绑定：`owner_username` 不再暴露给 LLM 填写，而是由后端按当前 `AgentRequest` 绑定，避免模型填错用户导致隔离风险。
- live 测试已验证真实 LangGraph Agent 可以完成 `file_lookup -> translation`。
- `TranslationAgentTool` 已增加常见目标语言别名规范化，将 `en/english/英文` 等统一为 `英语`，保持下游任务字段一致。
- 已补充受控 live Agent 工具选择测试，覆盖 `file_lookup -> spi` 和 `file_lookup -> diff`；默认跳过，仅显式配置 API key 时运行。
- 已新增 `WebSearchAgentTool` 和 `WebSearchService` 抽象，默认使用禁用态 service，不进行外网调用；已注册为可选 LangChain/LangGraph 工具并补充单元测试。
- Docker 打包范围已收敛：后端镜像只复制 `backend/app`、`backend/scripts`、`backend/legacy`，不再复制旧 `src/` 原型目录；compose 不再挂载 `src/` 和根目录 `parse_spi/`。
- 已新增 `docs/docker-deploy.md`，记录另一台电脑构建、启动、创建用户和访问方式。
- 已进入阶段 6 的第一小步：新增 `TaskExecutor` 抽象和默认 `SynchronousTaskExecutor`，并将 translation/SPI/diff 的 `create_task` 拆成“创建任务 + 提交执行器 + `_run_task` 执行业务”的边界；默认仍同步执行，保持现有 API 行为不变，后续可替换为后台线程、Celery 或 RQ。
- 已新增 `backend/tests/test_task_executor.py`，覆盖同步执行器立即运行，以及注入延迟执行器时 translation 任务先保持 `pending`、执行后变为 `succeeded`。
- 已完成阶段 6 的进程内后台线程执行器：新增 `ThreadPoolTaskExecutor`，由 FastAPI lifespan 创建并在应用关闭时 shutdown；通过 `SEKI_TASK_EXECUTOR=thread` 启用，通过 `SEKI_TASK_EXECUTOR_MAX_WORKERS` 控制线程数。
- 为避免请求结束后复用已关闭连接，translation/SPI/diff 后台执行路径会在线程中重新打开数据库连接并重建 service，同时沿用当前 workspace/work_dir/legacy 配置。
- `.env.example` 和 `backend/README.md` 已补充任务执行器配置说明；默认仍为 `sync`，不改变当前本地调试和测试行为。
- 已整理项目根目录：旧原型目录和旧依赖文件已移动到 `old/`，包括旧 `src/`、`parse_spi/`、`translate/`、`workspace/`、`tbox_docs/`、`tbox_vector_db/`、`parent_store/`、旧根 `.env` 和旧 `requirements*.txt`；根 `.env` 已用新框架 `.env.example` 重新生成。
- 当前自动化环境未放行外网 live 测试调用，用户可在本机终端手动运行 `.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py -m live`。
- 当前自动化环境未放行 `docker compose build`，用户可在本机终端手动运行 `docker compose build && docker compose up -d`。
- 下一批建议在用户确认后继续阶段 6：选择“后台线程执行器（无新依赖、适合本机 MVP）”或“Celery/RQ + Redis（更接近生产高并发形态，但需要新增服务和依赖）”。

## 当前依赖状态

后端虚拟环境当前已有：

- `langchain-core`
- `langgraph`
- `langchain`
- `langchain-openai`

当前版本：

- `langgraph==1.2.0`
- `langchain==1.3.1`
- `langchain-openai==1.2.1`
- `langchain-core==1.4.0`

曾尝试自动安装 `langgraph langchain langchain-openai` 失败，随后用户已手动安装成功。

已新增基于现有 `langchain-core` 的 LangChain tool 包装层：

- `backend/app/services/langchain_tool_adapter.py`
- `backend/tests/test_langchain_tool_adapter.py`

已新增 LangGraph graph factory：

- `backend/app/services/langgraph_agent_factory.py`
- `backend/tests/test_langgraph_agent_factory.py`

当前默认运行时已收敛为 LangGraph runner；`RuleBasedAgentRunner` 只作为单元测试/显式注入调试工具保留。运行真实 Agent 需要在后端环境变量中提供 `SEKI_RAG_API_KEY`。

LangGraph runner 调用 graph 时必须传入 checkpointer config：

```python
config = {
    "configurable": {
        "thread_id": f"{owner_username}:{conversation_id}",
        "checkpoint_ns": "seki-agent",
    }
}
graph.invoke(payload, config=config)
```

这个修复已在 `LangGraphAgentRunner.run(...)` 中完成，并有单元测试覆盖。

LangChain `create_agent` 的返回通常是 `{"messages": [...]}`，不一定包含 `answer` 字段。
`LangGraphAgentRunner._to_response(...)` 已兼容：

- 优先读取 `result["answer"]`。
- 如果没有 `answer`，读取 `result["messages"]` 中最后一条 message 的 `content`。
- 支持 dict message、对象 message，以及 list content 中的 `text/content`。

Live Agent 测试默认跳过。需要真实模型烟测时设置：

```powershell
$env:SEKI_RUN_LIVE_AGENT_TESTS='true'
$env:SEKI_RAG_API_KEY='你的 key'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py -m live
```

## 最近验证命令

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py backend\tests\test_langgraph_agent_factory.py backend\tests\test_langchain_tool_adapter.py backend\tests\test_langgraph_agent_runner.py backend\tests\test_agent_runner.py backend\tests\test_agent_tools.py backend\tests\test_agent_service.py backend\tests\test_chat.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_task_executor.py backend\tests\test_translation.py backend\tests\test_spi.py backend\tests\test_diff.py backend\tests\test_agent_tools.py backend\tests\test_agent_service.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_task_executor.py backend\tests\test_translation.py backend\tests\test_spi.py backend\tests\test_diff.py backend\tests\test_agent_tools.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_health.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_translate_excel_legacy.py backend\tests\test_translation.py backend\tests\test_spi.py backend\tests\test_files.py
cd frontend
npm run build
npm run lint
```

最近验证结果：

- Agent/Chat 相关后端测试 24 个通过，1 个按环境/配置跳过。
- 任务执行器与 translation/SPI/diff/Agent service 相关后端测试 29 个通过。
- 后台线程执行器接入后的受影响后端测试 37 个通过。
- Excel inlineStr 翻译、单元级容错、translation、SPI、files 相关后端测试已通过；最近一次翻译专项测试 7 个通过。
- 前端 build 通过。
- 前端 lint 通过。
- 最近一次前端任务状态持久化改动后，`npm run build` 和 `npm run lint` 均通过。
- 统一任务历史接口改动后，`backend/tests/test_tasks.py backend/tests/test_translation.py backend/tests/test_spi.py backend/tests/test_diff.py backend/tests/test_task_executor.py` 共 22 个后端测试通过；前端 `npm run build` 和 `npm run lint` 通过。
- 前端任务历史页接入后，`backend/tests/test_tasks.py` 4 个后端测试通过；前端 `npm run build` 和 `npm run lint` 通过。
- 长任务协作式取消接入后，`backend/tests/test_tasks.py backend/tests/test_task_executor.py backend/tests/test_translation.py backend/tests/test_spi.py backend/tests/test_diff.py` 共 26 个后端测试通过；前端 `npm run build` 和 `npm run lint` 通过。
- code_agent handoff 骨架接入后，Agent/Chat 相关后端测试 34 个通过、1 个按环境跳过；前端 `npm run build` 和 `npm run lint` 通过。
- 本次 handoff/API key 契约修正后，`backend/tests/test_agent_handoff_tools.py backend/tests/test_multi_agent_graph_factory.py backend/tests/test_langgraph_agent_factory.py backend/tests/test_langgraph_agent_runner.py backend/tests/test_agent_runner.py backend/tests/test_agent_service.py backend/tests/test_chat.py` 共 37 个通过、1 个按环境跳过；前端 `npm run build` 和 `npm run lint` 通过。
- 本次新增 code agent 设计文档，无代码执行改动，未新增依赖。
- 本次 `CodeExecutionService` 阶段 A 后端测试：`backend/tests/test_code_execution_service.py backend/tests/test_agent_handoff_tools.py backend/tests/test_multi_agent_graph_factory.py backend/tests/test_langgraph_agent_runner.py backend/tests/test_agent_runner.py` 共 34 个通过、1 个按环境跳过。
- 本次 code_agent 工具接入后端测试：`backend/tests/test_code_execution_service.py backend/tests/test_code_langchain_tool_adapter.py backend/tests/test_code_agent_factory.py backend/tests/test_agent_handoff_tools.py backend/tests/test_multi_agent_graph_factory.py backend/tests/test_langgraph_agent_factory.py backend/tests/test_langgraph_agent_runner.py backend/tests/test_agent_runner.py backend/tests/test_agent_service.py backend/tests/test_chat.py` 共 55 个通过、1 个按环境跳过。
- 本次受限 Python 脚本执行接入后端测试：同一组 Agent/code 测试共 61 个通过、1 个按环境跳过。
- 本次确认式删除第一阶段接入后端测试：同一组 Agent/code 测试共 65 个通过、1 个按环境跳过。
- 本次命令白名单接入后端测试：同一组 Agent/code 测试共 71 个通过、1 个按环境跳过。

## 本地运行提示

根 `.env` 当前已修正为 Windows 本地路径，指向：

```powershell
D:\seki\AI\Langchain\seki_agent\data\db\seki_agent.db
```

注意：`.env.example` 保留 Docker Compose 默认路径 `/app/data/...`。如果直接复制 `.env.example` 到根 `.env` 后在本机裸跑后端，会导致登录脚本和后端读写 `\app\data\db\seki_agent.db`，从而出现“已创建用户但前端登录提示账号或密码错误”。本地裸跑时需要使用项目内 `data/` 的绝对路径，修改 `.env` 后必须重启后端。

`backend/scripts/create_user.py` 已增加数据库路径输出，用于确认账号写入的 DB 是否和后端一致。

最近联调修复：

- 文件名清洗已放宽，上传文件、生成文件和下载文件名会保留中文，只替换 Windows 非法字符。
- SPI 解析 API 已支持 `file_ids` 批量输入；多个 `.log` 会复制到同一个任务目录，由旧 `parse_SPI.py` 合并解析并生成一个 Excel。
- SPI/translation 任务响应新增 `result_filename`，前端下载结果时优先使用后端真实结果文件名，避免中文名或扩展名被前端猜错。
- 后端启动时会通过 `python-dotenv` 加载根 `.env` 中的裸变量，确保旧翻译器可以读取 `TRANSLATE_API_KEY`、`TRANSLATE_BASE_URL`、`TRANSLATE_LLM_MODEL` 等配置。
- 翻译结果下载名已修复为 `原文件名_目标语言.扩展名`；如果后端返回 `result_filename`，以前者为准。
- Excel 翻译器已补充 `xl/worksheets/sheet*.xml` 中 `inlineStr/str` 单元格文本翻译；此前只处理 `sharedStrings.xml`、drawing 和 chart，遇到部分 xlsx 会打印“未找到 sharedStrings.xml”并生成未翻译文件。现在若完全找不到可翻译文本，会失败并返回错误，不再假成功。
- 已修复日语翻译失败分支中 `ToolException` 未导入导致的 `name 'ToolException' is not defined`；同时 Excel sharedStrings/worksheet 分组翻译改为单元级容错，某个单元失败不会导致整组文本全部丢失。
- 已修复前端任务状态面板切换页面后消失的问题：translation/SPI/diff 页面会将最近一次任务缓存到 `localStorage`，页面重新挂载时先恢复 `TaskResultPanel`，再向后端刷新任务状态。缓存 key 分别为 `seki_last_translation_task`、`seki_last_spi_task`、`seki_last_diff_task`。
- 已新增统一任务只读接口：`GET /api/v1/tasks` 按更新时间聚合当前用户 translation/SPI/diff 任务，支持 `limit=1..200`；`GET /api/v1/tasks/{task_id}` 可按统一格式查询任务。当前统一响应包含 `task_id`、`type`、`status`、`result_file_id`、`error`、`created_at`、`updated_at`，还不是完整任务详情/取消/重试接口。
- 已新增长任务协作式取消：`POST /api/v1/tasks/{task_id}/cancel` 会把当前用户 pending/running 的 translation/SPI/diff 任务标记为 `cancelled`；任务执行开始和写入结果前会检查取消状态，避免取消后覆盖为成功。当前不能安全强杀已阻塞在线程内的旧脚本或外部 API 调用，任务会在返回检查点后停止写入结果。
- 前端 `任务历史` 页面已新增手动“终止”按钮，调用统一取消接口；当前不提供重试或直接下载结果。

由于默认 `data/db` 在当前环境曾出现 SQLite 写入权限问题，可临时使用：

```powershell
$env:SEKI_DATA_DIR='D:\seki\AI\Langchain\seki_agent\backend\runtime'
$env:SEKI_DATABASE_PATH='D:\seki\AI\Langchain\seki_agent\backend\runtime\db\seki_agent.db'
$env:SEKI_WORKSPACE_DIR='D:\seki\AI\Langchain\seki_agent\backend\runtime\workspace'
$env:SEKI_DIFF_WORK_DIR='D:\seki\AI\Langchain\seki_agent\backend\runtime\diff_work'
$env:SEKI_SPI_WORK_DIR='D:\seki\AI\Langchain\seki_agent\backend\runtime\spi_work'
$env:SEKI_TRANSLATION_WORK_DIR='D:\seki\AI\Langchain\seki_agent\backend\runtime\translation_work'
```

演示账号曾创建为：

- 用户名：`demo`
- 密码：`demo123`

## Pending Operation 最新状态

- 已新增 code agent pending operation 后端边界：`CodeOperationRepository`、`CodeOperationService`、`/api/v1/code-operations` API 和 schema。
- Chat/Agent 出口在 `data.requires_confirmation=true` 时会创建 pending operation，并把 `pending_operation` 返回给前端。
- 本轮不让 Chat HTTP 请求阻塞等待用户确认；agent 本轮结束，前端后续通过确认/取消 API 推进状态。
- 确认删除既有文件/目录已支持；确认未知 shell 命令暂不真实执行，会返回“确认后执行未知命令的策略尚未开放”。
- 确认执行结果会追加到同一个 conversation 的 assistant 消息中。
- 前端 Agent 入口已接入 pending operation：当前 assistant 消息下展示确认卡片，支持确认执行、取消和按当前 conversation 刷新待确认操作。
- code agent 工具层已接入 pending operation：`code_delete_path` 和 `code_run_allowed_command` 返回 `requires_confirmation` 时会立即创建 pending operation，工具结果包含 `pending_operation_id`，不再完全依赖最终 LLM 回答保留结构化数据。
- code agent 命令策略已配置化：`SEKI_CODE_AGENT_ALLOWED_COMMAND_PREFIXES` 命中直接执行，`SEKI_CODE_AGENT_CONFIRMED_COMMAND_PREFIXES` 命中先 pending、用户确认后执行；其他未知命令确认后仍不会执行。
- 后续可在这个持久化边界上接入前端确认 UI，或评估 LangGraph interrupt/resume。

最新验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_code_operation_service.py backend\tests\test_code_operations_api.py backend\tests\test_code_execution_service.py backend\tests\test_agent_service.py backend\tests\test_chat.py
```

结果：48 passed。

前端接入后最新验证：

```powershell
cd frontend
npm run build
npm run lint
cd ..
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_code_operation_service.py backend\tests\test_code_operations_api.py backend\tests\test_agent_service.py backend\tests\test_chat.py
```

结果：前端 build/lint 通过；后端 20 passed。

工具级 pending 和配置化命令策略验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_code_execution_service.py backend\tests\test_code_langchain_tool_adapter.py backend\tests\test_code_operation_service.py backend\tests\test_code_operations_api.py
```

结果：42 passed。

## Agent 入口可测状态

- 已新增 `ChatModelService`，用于普通聊天 fallback。
- 默认 `rule` runner 在 `use_knowledge_base=false` 时会调用普通聊天模型，而不是返回“未配置普通聊天模型”的占位提示。
- 普通聊天模型复用 `SEKI_RAG_BASE_URL`、`SEKI_RAG_MODEL_NAME` 和后端环境变量 `SEKI_RAG_API_KEY`。
- 前端 Agent 页提示已调整：关闭“使用知识库 / RAG”即可测试普通聊天。
- 默认运行时不再按关键词猜测 code_agent handoff，统一由 LangGraph Agent 通过 handoff tool 自主切换；`RuleBasedAgentRunner` 的关键词路由只在单元测试直接构造时使用。
- 已补齐 Agent 入口的短期记忆边界：`ChatRepository.list_messages(...)` 会读取当前用户当前 conversation 最近消息，`AgentService.ask(...)` 在写入本轮 user 消息前把历史传入 `AgentRequest.history`；`ChatModelService` 和 `LangGraphAgentRunner` 会把最近 20 条 user/assistant 历史带给模型/graph，保持用户、conversation、agent_name 隔离。
- 已补齐旧框架身份设定：`TBOX_AGENT_SYSTEM_PROMPT` 继续保留“畅星集团/SIS、本田、TSU、seki 开发的助手”的设定，并补回普通聊天职责、普通问题不乱用工具、未指定翻译目标语言时默认日语等旧 Agent 行为。
- 已新增 Chat SSE 流式接口：`POST /api/v1/chat/conversations/{conversation_id}/messages/stream` 返回 `event: delta` 和 `event: final`；前端 Agent 页面优先调用该接口并增量更新同一个 assistant 气泡，保留旧非流式接口作为“请求尚未开始输出时”的兼容兜底。
- 当前流式实现是接口层 SSE 增量输出：后端 runner 仍先完成一次 Agent 调用，再将最终 answer 分片推给前端。后续如果要实现真实模型 token 级流式，需要继续扩展 `AgentRunner`/`LangGraphAgentRunner` 的 streaming 协议，并接入 LangGraph/ChatOpenAI 的原生 stream。
- 已接回旧版火山/Feedcoop 风格联网搜索 provider：配置 `SEKI_WEB_SEARCH_API_KEY` 时启用；无 key 时工具返回未配置提示。
- Chat API 已移除前端临时联网搜索 key 输入，搜索 key 统一从后端环境变量读取。
- `RuleBasedAgentRunner` 仍有 `web_search` 关键词路由测试覆盖，但默认运行时不再使用它。
- 前端 Agent 入口已移除密钥输入框，密钥统一在后端 `.env` 管理。
- 前端 Agent 聊天区域已改为内部滚动，消息过多时滚动 `.chat-feed`，不再优先拉长整个页面。
- LangSmith 推荐沿用 LangChain/LangGraph 原生 tracing 环境变量：`LANGSMITH_TRACING=true`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT`，这样模型、工具、graph span 可自然进入 LangSmith；不建议在当前阶段自定义包一层 trace，以免破坏 LangGraph 原生链路。
- 已移除运行时 `SEKI_AGENT_RUNNER`、`SEKI_WEB_SEARCH_PROVIDER` 和关键词 handoff 环境开关；默认服务路径固定为 LangGraph runner，联网搜索只看后端环境火山 key。`RuleBasedAgentRunner` 只保留为单元测试/显式注入调试构件。

验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chat_model_service.py backend\tests\test_agent_runner.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_agent_handoff_tools.py backend\tests\test_multi_agent_graph_factory.py
```

结果：36 passed。

本轮 Agent 记忆、身份设定和 SSE 前端流式验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_runner.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_langgraph_agent_runner.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chat_model_service.py backend\tests\test_agent_tools.py backend\tests\test_code_operation_service.py backend\tests\test_code_operations_api.py backend\tests\test_multi_agent_graph_factory.py backend\tests\test_langgraph_agent_factory.py backend\tests\test_agent_handoff_tools.py backend\tests\test_chat.py backend\tests\test_agent_service.py
cd frontend
npm run build
npm run lint
```

结果：第一组后端 36 passed、1 skipped；第二组后端 45 passed；前端 build/lint 通过。

本轮 web_search、前端 key 和聊天框滚动验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_web_search_service.py backend\tests\test_agent_runner.py backend\tests\test_chat.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_runner.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_agent_tools.py backend\tests\test_langchain_tool_adapter.py
cd frontend
npm run build
npm run lint
```

结果：后端 21 passed；后端 46 passed；前端 build/lint 通过。

本轮 runner/web_search 配置收敛验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_langgraph_agent_runner.py backend\tests\test_agent_runner.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_web_search_service.py
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_tools.py backend\tests\test_langchain_tool_adapter.py backend\tests\test_langgraph_agent_factory.py backend\tests\test_multi_agent_graph_factory.py backend\tests\test_agent_handoff_tools.py
cd frontend
npm run build
npm run lint
```

结果：后端 40 passed、1 skipped；后端 25 passed；前端 build/lint 通过。

## 本轮现状梳理、文档和注释

用户要求先暂停继续大功能开发，整理当前工程状态：

- 删除不再需要的前端占位代码和 Vite 示例资产：
  - `frontend/src/pages/PlaceholderPage.tsx`
  - `frontend/src/assets/react.svg`
  - `frontend/src/assets/vite.svg`
  - `frontend/src/assets/hero.png`
- `frontend/src/App.tsx` 已移除 `PlaceholderPage` 引用，未知路由回退到登录页。
- 清理默认 runner 相关残留：`agent_runner_factory.py` 不再保留 `prefer_langgraph` 参数，运行时默认固定 LangGraph。
- 扫描 `PlaceholderPage|react.svg|vite.svg|hero.png|prefer_langgraph|SEKI_AGENT_RUNNER|SEKI_WEB_SEARCH_PROVIDER` 等关键字，除文档中“已移除”历史说明外无运行时代码残留。
- 修复 `CodeExecutionService.create_dir()` 中已有路径分支引用未定义变量 `recursive` 的 bug。

新增当前态文档：

- `docs/implementation-status.md`：基于当前代码整理大的已实现能力和待实现需求，后续当前规划优先看这个文件。
- `docs/file-structure.md`：说明根目录、backend、frontend、tests、old/legacy 的文件职责。
- `docs/user-guide.md`：说明本地启动前后端、创建用户、前端使用、Docker 部署/启动/用户管理、测试命令和常见问题。
- `docs/README.md` 已补齐上述新文档入口，并说明 `refactor-roadmap.md` 主要保留历史迭代记录。

已补中文注释/说明的当前有效代码主干：

- 后端入口、配置、鉴权、临时 API key、SQLite 连接、依赖注入。
- Chat API、AgentService、AgentRunner 协议、LangGraph runner/factory、Agent 工具、联网搜索。
- 文件服务、任务执行器、翻译任务服务、code pending operation 服务、聊天仓储。
- 前端 App 路由、ChatPage 关键状态和 SSE chat API。

注释策略：只给当前有效框架代码补“职责/边界/关键流程”说明，不对 `old/` 和 `backend/legacy/` 做批量注释，避免把旧原型和兼容代码误当成新框架主线。

验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_langgraph_agent_runner.py backend\tests\test_agent_runner.py backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_web_search_service.py backend\tests\test_agent_tools.py backend\tests\test_langchain_tool_adapter.py backend\tests\test_langgraph_agent_factory.py backend\tests\test_multi_agent_graph_factory.py backend\tests\test_agent_handoff_tools.py
cd frontend
npm run build
npm run lint
```

结果：后端 65 passed、1 skipped；前端 build/lint 通过。

## 本轮 Agent 入口改进

用户反馈的 5 个问题已处理：

- `frontend/index.html` 已改用 `/$this.Icon.ico` 作为网页图标。
- Agent 入口会把最近一次 `conversation_id` 缓存在 `localStorage`，页面重新进入时调用 `GET /api/v1/chat/conversations/{conversation_id}/messages` 恢复历史消息，可继续对话。
- `chat_messages` 现在会保存本轮 LangGraph 返回的 `tool` 消息；模型短期历史仍只回放 `user/assistant`，避免工具结果直接污染普通对话上下文。
- 前端 Agent 页和翻译页已删除 API key 输入；Chat API 请求体不再接收 `api_key` / `web_search_api_key`。密钥统一通过后端环境变量配置。
- `conversations` 表新增 `active_agent` 字段并兼容旧表自动 `ALTER TABLE`；`AgentService` 每轮结束后记录 `active_agent`，下一轮会把它作为 `AgentRequest.agent_name` 和 LangGraph `active_agent` 传入，使 `route_initial` 默认从上一轮结束 agent 开始。

验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_service.py backend\tests\test_chat.py backend\tests\test_langgraph_agent_runner.py backend\tests\test_multi_agent_graph_factory.py
cd frontend
npm run lint
npm run build
```

结果：后端 35 passed、1 skipped；前端 lint/build 通过。

## 本轮 code_agent 路由和工作目录修复

- 修复切到 `code_agent` 后下一轮命中 `CodeAgentUnavailableRunner` 的问题：默认生产 runner 现在直接返回 LangGraph multi-agent runner，由图内 `route_initial` 按持久化的 `active_agent` 进入 main/code agent。
- `CodeExecutionService` 新增 `writable_roots`，读取/执行允许根和写入/删除工作根分离。
- 默认 code agent 可读取/执行当前用户 workspace、项目根目录和共享 skills 目录；相对路径默认落到 `data/workspace/{username}`，写入和删除限制在该用户 workspace 下。
- code agent prompt 已补充：读取/运行项目根或 skills 文件要使用明确路径，但不要把新文件写到项目根目录。

验证：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_langgraph_agent_runner.py backend\tests\test_agent_runner.py backend\tests\test_multi_agent_graph_factory.py backend\tests\test_code_execution_service.py backend\tests\test_code_langchain_tool_adapter.py backend\tests\test_code_agent_factory.py backend\tests\test_agent_service.py backend\tests\test_chat.py
cd frontend
npm run build
```

结果：后端 86 passed、1 skipped；前端 build 通过。
