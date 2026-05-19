# 当前上下文摘要

本文用于在长对话压缩后快速恢复项目状态。

## 项目目标

将旧 `src/` 下基于 Streamlit/LangGraph/LangChain 的公司业务 Agent，重构为工程化前后端分离系统：

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
- `rag`：当前最小 RAG 回答能力，懒加载旧 `src/rag.py`、`src/vector_db.py`。
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
- 旧 `src/multi_agent.py` 的闭包上下文不适合多用户并发，后续必须替换为 `owner_username + conversation_id` 隔离。
- `AgentService` 默认 runner 已注入 RAG、translation、SPI、diff service；Agent 对话入口和前端手动入口共享这些 service。
- Chat API 响应已保留 Agent runner 的 `route` 和 `data` 字段。
- 前端 Agent 对话页已展示结构化工具结果，包括工具路由、任务 ID、状态、结果文件 ID 和错误信息。
- 已完成旧 `src/` Agent 工具链差距梳理：RAG/translation/SPI/diff 已迁移到新后端 service/tool adapter；`web_search`、`code_agent`、多 Agent 交接、长上下文摘要和文件名到 `file_id` 解析仍待设计。
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
- 当前自动化环境未放行外网 live 测试调用，用户可在本机终端手动运行 `.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py -m live`。
- 当前自动化环境未放行 `docker compose build`，用户可在本机终端手动运行 `docker compose build && docker compose up -d`。
- 下一批推荐先验证 Docker 镜像在本机/另一台电脑跑通；若通过，再进入异步任务队列抽象设计。

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
cd frontend
npm run build
npm run lint
```

最近验证结果：

- Agent/Chat 相关后端测试 24 个通过，1 个按环境/配置跳过。
- 前端 build 通过。
- 前端 lint 通过。

## 本地运行提示

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
