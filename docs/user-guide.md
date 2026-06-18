# 使用说明书

本文说明如何在本地和 Docker 环境运行 Seki Agent，以及如何管理用户。

## 1. 本地准备

### 1.1 后端 Python 环境

在项目根目录执行：

```powershell
cd D:\seki\cc\seki_agent
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

如果还没有虚拟环境（当前开发环境使用 Python 3.12）：

```powershell
cd D:\seki\cc\seki_agent\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

注意：虚拟环境内记录的是基础解释器的绝对路径。如果项目目录整体搬移或换机器，
原 `.venv` 会失效（报 `did not find executable`），需要删除后重新创建。

### 1.2 前端 Node 环境

```powershell
cd D:\seki\cc\seki_agent\frontend
npm install
```

## 2. 本地配置

### 2.1 PostgreSQL / Redis

开发阶段不需要安装 Windows 版 PostgreSQL。推荐方式是：

- PostgreSQL/Redis 用 Docker Compose 启动。
- 后端和前端在 Windows 本机裸跑，方便调试和跑测试。

先启动依赖服务：

```powershell
cd D:\seki\cc\seki_agent
docker compose up -d postgres redis
```

根目录 `.env` 本机裸跑建议使用 Windows 路径和主机端口：

```env
SEKI_DATA_DIR="D:/seki/cc/seki_agent/data"
SEKI_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/seki_agent"
SEKI_WORKSPACE_DIR="D:/seki/cc/seki_agent/data/workspace"
SEKI_DIFF_WORK_DIR="D:/seki/cc/seki_agent/data/diff_work"
SEKI_SPI_WORK_DIR="D:/seki/cc/seki_agent/data/spi_work"
SEKI_TRANSLATION_WORK_DIR="D:/seki/cc/seki_agent/data/translation_work"
SEKI_SKILLS_DIR="D:/seki/cc/seki_agent/data/skills"
SEKI_LEGACY_SRC_DIR="D:/seki/cc/seki_agent/backend/legacy"
SEKI_CELERY_BROKER_URL="redis://127.0.0.1:6379/0"
```

如果本机已有 Windows 版 PostgreSQL 占用了 `5432`，可以把 compose 的端口改为例如 `15432:5432`，并把本机 `.env` / `SEKI_TEST_DATABASE_URL` 中的端口改为 `15432`。

### 2.2 模型与业务配置

模型和搜索配置：

```env
SEKI_RAG_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
SEKI_RAG_MODEL_NAME="qwen-plus"
SEKI_RAG_API_KEY="你的千问或兼容 OpenAI API key"

SEKI_WEB_SEARCH_API_KEY="你的火山搜索 key"
SEKI_WEB_SEARCH_API_URL="https://open.feedcoopapi.com/search_api/web_search"
```

RAG 知识库数据目录（由 `backend/legacy/vector_db.py`、`rag.py` 读取；知识库源文件
和向量库由本地维护者管理，存放在 `data/` 下）：

```env
TBOX_DOCS_DIR="C:/seki/seki_agent/seki_agent/data/tbox_docs"
PARENT_STORE_DIR="C:/seki/seki_agent/seki_agent/data/parent_store"
VECTOR_DB_DIR="C:/seki/seki_agent/seki_agent/data/tbox_vector_db"
EMBEDDING_MODEL="text-embedding-v4"
EMBEDDING_API_KEY="重建向量库时需要的 embedding key"
```

翻译 legacy 逻辑读取：

```env
TRANSLATE_API_KEY="你的翻译模型 key"
TRANSLATE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
TRANSLATE_LLM_MODEL="qwen-plus"
```

Agent token 限额：

```env
SEKI_MAX_CONVERSATION_TOKENS=200000
```

当单个 conversation 累计 token 达到该基数时，前端会弹窗确认是否继续；确认后上限提高到 2 倍、3 倍，以此类推。设为 `0` 可关闭限制。

自建追踪和结构化日志无需额外服务，记录会写入 PostgreSQL：

```env
SEKI_LOG_LEVEL="INFO"
SEKI_LOG_FORMAT="json"
```

LangSmith 仍可作为 LangGraph 原生链路调试补充：

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY="你的 LangSmith key"
LANGSMITH_PROJECT="seki-agent-local"
```

## 3. 本地启动

### 3.1 启动后端

```powershell
cd D:\seki\cc\seki_agent\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

### 3.2 启动前端

另开一个终端：

```powershell
cd D:\seki\cc\seki_agent\frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 4. 用户管理

### 4.1 创建或更新用户

```powershell
cd D:\seki\cc\seki_agent\backend
.\.venv\Scripts\python.exe scripts\create_user.py demo demo123
```

脚本会打印实际连接的数据库 URL。它必须和后端 `.env` 中 `SEKI_DATABASE_URL` 一致。

创建管理员用户：

```powershell
.\.venv\Scripts\python.exe scripts\create_user.py admin admin123 --admin
```

管理员登录后可以在“用户管理”页面查询、创建和删除用户。系统禁止管理员删除自己。

### 4.2 登录

前端打开登录页，输入：

```text
用户名：demo
密码：demo123
```

## 5. 前端页面使用

- 文件管理：先上传需要翻译、解析或比较的文件。
- Agent 入口：
  - 可直接让 Agent 查知识库、联网搜索、找文件、创建翻译/SPI/diff 任务。
  - 切换到其他页面再回来，会恢复最近一次对话并可继续发送消息。
  - 生成中可点击“停止”中断当前 SSE 请求；本轮未完成回答不会作为最终 assistant 消息落库。
  - 页面会实时展示本轮和本会话 token 消耗；达到配置上限后会弹窗询问是否继续。
  - code agent 高风险操作会出现确认卡片：删除既有内容、执行未知命令、覆盖写入既有文件都需要用户确认；覆盖写入的确认卡片会显示新旧内容的 diff 预览。
  - code agent 的每次工具执行（成功、失败、被拒绝）都会写入审计表，可通过 `GET /api/v1/code-operations/audit` 查询当前用户的操作记录。
- 文档翻译：手动选择 workspace 文件并创建翻译任务。
- SPI log 解析：选择 `.log` 文件创建解析任务。
- 版本差分：选择两个 `.tar.gz` 文件创建差分任务。
- 任务历史：查看和取消最近任务。
- Trace：查看当前用户自己的 Agent 运行记录、工具调用、token 用量、耗时和错误。
- 用户管理：管理员可查询、创建和删除用户。

## 6. Docker 部署

### 6.1 准备 Docker `.env`

Docker 环境建议从模板复制：

```powershell
copy .env.example .env
```

Docker 中路径应使用 `/app/data/...`，例如：

```env
SEKI_DATA_DIR="/app/data"
SEKI_DATABASE_URL="postgresql://postgres:postgres@postgres:5432/seki_agent"
SEKI_WORKSPACE_DIR="/app/data/workspace"
SEKI_LEGACY_SRC_DIR="/app/backend/legacy"
```

### 6.2 构建并启动

```powershell
cd C:\seki\seki_agent\seki_agent
docker compose up --build -d
```

查看状态：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

访问：

```text
前端：http://127.0.0.1:5173
后端健康检查：http://127.0.0.1:8000/api/v1/health
```

### 6.3 Docker 中创建用户

```powershell
docker compose exec backend python scripts/create_user.py demo demo123
```

### 6.4 停止服务

```powershell
docker compose down
```

保留数据时不要删除 `data/`。如果要完全清空本地运行数据，需要手动清理 `data/`，这会删除用户、任务记录和上传文件。

PostgreSQL 数据在 Docker volume `seki_agent_postgres_data` 中，不在 `data/db/*.db` 文件里。需要迁移数据库时使用 `pg_dump` / `pg_restore`。

## 7. 测试和构建

后端测试：

```powershell
cd D:\seki\cc\seki_agent
.\backend\.venv\Scripts\python.exe -m pytest
```

测试会连接：

```env
SEKI_TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/seki_agent_test"
```

如果使用非默认端口，先设置该环境变量再运行 pytest。

前端检查：

```powershell
cd C:\seki\seki_agent\seki_agent\frontend
npm run build
npm run lint
```

live Agent 测试默认跳过。需要真实模型 smoke test 时：

```powershell
$env:SEKI_RUN_LIVE_AGENT_TESTS='true'
$env:SEKI_RAG_API_KEY='你的 key'
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_live_langgraph_agent.py -m live
```

## 8. 常见问题

### 登录失败但用户创建成功

通常是 `create_user.py` 连接的数据库和后端读取的数据库不一致。检查脚本输出的数据库 URL，并确认 `.env` 中 `SEKI_DATABASE_URL` 是同一个地址。

### pytest 提示 PostgreSQL 连接超时

先确认 Docker Desktop 已启动，并执行：

```powershell
docker compose up -d postgres redis
docker compose ps
```

`postgres` 应为 healthy，且端口显示 `0.0.0.0:5432->5432/tcp`。

### pytest 提示 Windows Temp 权限错误

这是本机临时目录权限问题，不是业务断言失败。可以尝试指定项目内临时目录：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest --basetemp=backend\.pytest_tmp_local -p no:cacheprovider
```

### Agent 提示缺少 API key

在 `.env` 配置 `SEKI_RAG_API_KEY`，然后重启后端。

### 联网搜索不可用

在 `.env` 配置 `SEKI_WEB_SEARCH_API_KEY`，然后重启后端。

### Docker 前端访问不到后端

确认 `docker-compose.yml` 中前端构建参数：

```yaml
VITE_API_BASE_URL: "http://localhost:8000/api/v1"
```

如果部署到另一台机器，需要把这里改成浏览器能访问到的后端地址。
