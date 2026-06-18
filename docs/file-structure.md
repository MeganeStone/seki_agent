# 文件结构说明

本文说明当前项目主要文件职责。`old/` 是重构前原型，保留用于对照迁移；`backend/legacy/` 是当前后端仍会调用的兼容逻辑。

## 根目录

- `.env`：本地运行配置，包含数据库路径、工作目录、模型配置等。
- `.env.example`：环境变量模板，适合复制后按本机或 Docker 修改。
- `docker-compose.yml`：同时启动后端和前端容器。
- `pytest.ini`：pytest 配置。
- `README.md`：项目最简入口说明。

## backend

- `backend/Dockerfile`：后端容器镜像构建文件。
- `backend/requirements.txt`：后端 Python 依赖。
- `backend/README.md`：后端本地开发、配置和测试说明。

### backend/app

- `main.py`：FastAPI 应用入口，创建任务执行器、配置 CORS、注册 API 路由。

### backend/app/core

- `config.py`：集中读取环境变量，形成 `Settings`。
- `logging.py`：结构化日志配置，按业务隔离到不同文件（access/app/audit/trace/error），按大小轮转（50MB/文件，保留 10 个备份），自动注入当前用户名。
- `context.py`：请求级上下文变量（ContextVar），用于在中间件和日志之间传递当前用户信息。
- `security.py`：密码哈希、JWT 创建和解析。
- `api_keys.py`：临时环境变量上下文，供 legacy 调用时复用统一配置。

### backend/app/api

- `router.py`：聚合所有 v1 API router。
- `dependencies.py`：FastAPI 依赖注入入口，创建 service、读取当前用户、读取任务执行器。

### backend/app/api/v1

- `auth.py`：登录和当前用户接口。
- `files.py`：文件上传、列表、下载、删除接口。
- `chat.py`：Agent conversation 创建、历史消息、非流式消息、SSE 流式消息接口。
- `translation.py`：翻译任务接口。
- `spi.py`：SPI 解析任务接口。
- `diff.py`：版本差分任务接口。
- `tasks.py`：统一任务历史和取消接口。
- `code_operations.py`：code agent pending operation 查询、确认、取消接口。
- `health.py`：健康检查接口。

### backend/app/schemas

- `auth.py`：用户、登录请求和 token 响应模型。
- `files.py`：文件读模型。
- `chat.py`：对话请求、响应和来源模型。
- `translation.py`：翻译任务请求/响应模型。
- `spi.py`：SPI 解析任务请求/响应模型。
- `diff.py`：版本差分任务请求/响应模型。
- `tasks.py`：统一任务响应模型。
- `code_operations.py`：pending operation 请求/响应模型。

### backend/app/repositories

- `user_repository.py`：用户表读写。
- `file_repository.py`：文件元数据表读写。
- `chat_repository.py`：conversation 和 chat message 表读写。
- `translation_repository.py`：翻译任务表读写。
- `spi_repository.py`：SPI 任务表读写。
- `diff_repository.py`：差分任务表读写。
- `code_operation_repository.py`：code pending operation 表读写。
- `code_audit_repository.py`：code agent 操作审计表读写。

### backend/app/services

- `auth_service.py`：用户创建、验证密码、登录 token 生成。
- `file_service.py`：文件保存、隔离、下载路径校验、删除。
- `translation_service.py`：翻译任务创建、执行、结果文件保存。
- `spi_service.py`：SPI 解析任务创建、执行、结果文件保存。
- `diff_service.py`：版本差分任务创建、执行、结果保存。
- `task_service.py`：统一任务列表、查询和取消。
- `task_executor.py`：同步执行器和线程池执行器抽象。
- `rag_service.py`：懒加载 legacy RAG 能力。
- `web_search_service.py`：联网搜索 provider，目前支持火山/Feedcoop 兼容 API。
- `chat_model_service.py`：普通聊天模型封装，目前主要保留给测试和显式注入。
- `agent_prompts.py`：主 Agent 系统 prompt。
- `agent_service.py`：Chat API 背后的 Agent conversation 边界，负责消息持久化和 runner 调用。
- `agent_runner.py`：Agent runner 协议、LangGraph handoff 包装、测试用 rule runner。
- `agent_runner_factory.py`：默认运行时 runner 工厂，目前固定创建 LangGraph runner。
- `agent_tools.py`：RAG、web_search、file_lookup、translation、SPI、diff 的 Agent 工具适配。
- `langchain_tool_adapter.py`：把内部 Agent 工具包装为 LangChain `StructuredTool`。
- `langgraph_agent_factory.py`：创建主 TBOX LangGraph agent。
- `langgraph_agent_runner.py`：调用 LangGraph graph 的 runner 边界。
- `multi_agent_graph_factory.py`：组合 main agent 和 code agent 子图。
- `agent_handoff_tools.py`：主 Agent 到 code agent 的 handoff 工具。
- `code_execution_service.py`：受限本地文件/命令/Python 脚本执行能力。
- `code_agent_tools.py`：code agent 的工具适配。
- `code_langchain_tool_adapter.py`：把 code agent 工具包装为 LangChain tool。
- `code_agent_factory.py`：创建 code agent graph。
- `code_operation_service.py`：pending operation 业务逻辑和审计查询。
- `code_audit_service.py`：默认审计 sink（独立短连接落库）和审计行转换。

### backend/db

- `postgres.py`：PostgreSQL 连接创建、请求级连接依赖和 dict row 设置。

### backend/scripts

- `create_user.py`：创建或更新本地用户账号。

### backend/legacy

当前仍被 service 调用的旧实现收敛目录：

- `translate_*.py`、`tbox_custom_translator.py`：Office 文档翻译逻辑。
- `parse_SPI.py`、`parse_spi/`：SPI log 解析逻辑和模板/配置。
- `bin_srcdiff.sh`、`lib_srcdiff.sh`：版本差分脚本。
- `rag.py`、`vector_db.py`、`rerank.py` 等：RAG 和向量库兼容逻辑。

## frontend

- `frontend/Dockerfile`：前端容器镜像构建文件。
- `frontend/package.json`：前端依赖和脚本。
- `frontend/vite.config.ts`：Vite 配置。

### frontend/src

- `main.tsx`：React 应用挂载入口。
- `App.tsx`：整体布局、导航、健康检查和页面路由。
- `App.css`：主要页面样式。
- `index.css`：全局基础样式。

### frontend/src/api

- `client.ts`：API base URL、健康检查、通用下载辅助。
- `auth.ts`：登录和当前用户 API。
- `files.ts`：文件管理 API。
- `chat.ts`：对话创建、非流式消息、SSE 流式消息 API。
- `translation.ts`：翻译任务 API。
- `spi.ts`：SPI 任务 API。
- `diff.ts`：差分任务 API。
- `tasks.ts`：统一任务历史和取消 API。
- `codeOperations.ts`：pending operation API。

### frontend/src/pages

- `LoginPage.tsx`：登录页。
- `ChatPage.tsx`：Agent 对话页，支持历史恢复、流式显示、工具结果和 pending operation。
- `AdminUsersPage.tsx`：管理员用户管理页。
- `TracePage.tsx`：Agent 自建追踪查看页。
- `FilesPage.tsx`：文件管理页。
- `TranslationPage.tsx`：文档翻译页。
- `SpiPage.tsx`：SPI 解析页。
- `DiffPage.tsx`：版本差分页。
- `TasksPage.tsx`：任务历史页。

### frontend/src/components

- `TaskResultPanel.tsx`：翻译/SPI/diff 共享的任务状态和结果展示组件。

### frontend/src/types

各 API 对应的 TypeScript 类型定义。

## tests

- `backend/tests/`：后端单元测试和 API 测试。
- live LangGraph 测试默认跳过，需要显式环境变量和真实 API key。

## data

运行数据目录，不作为源码资产；Docker Compose 将其整体挂载到容器 `/app/data`：

- `workspace/{username}/`：各用户文件工作区。
- `diff_work/`、`spi_work/`、`translation_work/`：各任务类型的工作目录。
- `tbox_docs/`：RAG 知识库源文档（本地维护者管理）。
- `parent_store/`：RAG 父文档存储。
- `tbox_vector_db/`：Chroma 向量库。
- `logs/`：按业务隔离的日志文件，每天轮转保留 30 天。
  - `access.log`：HTTP 请求日志（`seki.request`）。
  - `app.log`：业务主日志（agent、task、auth、admin 等）。
  - `audit.log`：安全审计日志（code agent 操作、用户管理）。
  - `trace.log`：Agent 运行追踪日志（`seki.trace`）。
  - `error.log`：所有 ERROR 级别日志的副本（快速定位问题）。

PostgreSQL 数据不再是 `data/db/*.db` 文件；Docker Compose 默认使用
`postgres_data` volume 保存数据库。`data/` 仍保存用户文件、任务工作目录和
legacy RAG 运行数据。

## old

- `old/src/`：重构前 Streamlit/LangGraph/LangChain 原型源码，保留作迁移对照。
- `old/parse_spi/`：旧 SPI 解析的多套 settings 变体和模板（backend/legacy 只收敛了当前在用的一套）。
- 旧 workspace 数据、空 translate 目录、requirements 快照、旧 `.env`、旧用户库已删除；
  RAG 知识库数据（tbox_docs/parent_store/tbox_vector_db）已迁移到 `data/`。
- 当前运行时不直接依赖 `old/`。
