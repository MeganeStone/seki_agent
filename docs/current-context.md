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
- `agent_runner`：`AgentRunner` 协议和 `RuleBasedAgentRunner`。
- `langgraph_agent_runner`：可选 LangGraph runner 最小边界，支持 fake graph 测试。

## 已完成前端页面

- 登录/健康检查。
- 文件管理。
- 文档翻译。
- SPI log 解析。
- 版本差分比较。
- Agent 入口：通过 Chat API 调用后端 AgentService/AgentRunner，前端导航已明确显示为 `Agent 入口`。
- `TaskResultPanel` 通用任务结果组件，已被 translation、SPI、diff 页面复用。
- Agent 对话页已支持按 `route + task_id` 查询 translation/SPI/diff 任务状态，并可按 `result_file_id` 下载工具结果文件。

## 关键设计

- `Chat API -> AgentService -> AgentRunner -> Agent tool adapter -> backend service`
- Agent tool adapter 只做参数映射、调用 service、整理返回；不做业务逻辑。
- service 层负责业务规则、持久化、文件隔离。
- 长任务工具返回 task/result_file_id，前端或 Agent 可查询/下载。
- 旧 `old/src/multi_agent.py` 的闭包上下文不适合多用户并发，后续必须替换为 `owner_username + conversation_id` 隔离。
- `AgentService` 默认 runner 已注入 RAG、translation、SPI、diff service；Agent 对话入口和前端手动入口共享这些 service。
- Chat API 响应已保留 Agent runner 的 `route` 和 `data` 字段。
- 前端 Agent 对话页已展示结构化工具结果，包括工具路由、任务 ID、状态、结果文件 ID 和错误信息。
- 已完成旧 `old/src/` Agent 工具链差距梳理：RAG/translation/SPI/diff 已迁移到新后端 service/tool adapter；`web_search`、`code_agent`、多 Agent 交接、长上下文摘要和文件名到 `file_id` 解析仍待设计。
- 已新增 `FileLookupAgentTool`，让 LangGraph Agent 能按当前用户 workspace 文件名/后缀查找文件 ID，降低用户手动输入 `file_id` 的门槛。
- 已补充 Agent 多步工具链契约测试，覆盖 `file_lookup -> translation`、`file_lookup -> spi`、`file_lookup -> diff` 的 file_id 传递。
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

当前默认仍使用 `SEKI_AGENT_RUNNER="rule"`，如需启用 LangGraph runner，配置 `SEKI_AGENT_RUNNER="langgraph"` 并提供 `SEKI_RAG_API_KEY`。

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
