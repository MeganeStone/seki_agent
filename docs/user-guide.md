# 使用说明书

本文说明如何在本地和 Docker 环境运行 Seki Agent，以及如何管理用户。

## 1. 本地准备

### 1.1 后端 Python 环境

在项目根目录执行：

```powershell
cd D:\seki\AI\Langchain\seki_agent
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

如果还没有虚拟环境：

```powershell
cd D:\seki\AI\Langchain\seki_agent\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 1.2 前端 Node 环境

```powershell
cd D:\seki\AI\Langchain\seki_agent\frontend
npm install
```

## 2. 本地配置

根目录 `.env` 应使用 Windows 本地路径，例如：

```env
SEKI_DATA_DIR="D:/seki/AI/Langchain/seki_agent/data"
SEKI_DATABASE_PATH="D:/seki/AI/Langchain/seki_agent/data/db/seki_agent.db"
SEKI_WORKSPACE_DIR="D:/seki/AI/Langchain/seki_agent/data/workspace"
SEKI_DIFF_WORK_DIR="D:/seki/AI/Langchain/seki_agent/data/diff_work"
SEKI_SPI_WORK_DIR="D:/seki/AI/Langchain/seki_agent/data/spi_work"
SEKI_TRANSLATION_WORK_DIR="D:/seki/AI/Langchain/seki_agent/data/translation_work"
SEKI_LEGACY_SRC_DIR="D:/seki/AI/Langchain/seki_agent/backend/legacy"
```

模型和搜索配置：

```env
SEKI_RAG_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
SEKI_RAG_MODEL_NAME="qwen-plus"
# 可选：也可以在前端 Agent 页面输入临时千问 key
SEKI_RAG_API_KEY="你的千问或兼容 OpenAI API key"

# 可选：也可以在前端 Agent 页面输入临时火山搜索 key
SEKI_WEB_SEARCH_API_KEY="你的火山搜索 key"
SEKI_WEB_SEARCH_API_URL="https://open.feedcoopapi.com/search_api/web_search"
```

翻译 legacy 逻辑读取：

```env
TRANSLATE_API_KEY="你的翻译模型 key"
TRANSLATE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
TRANSLATE_LLM_MODEL="qwen-plus"
```

LangSmith 追踪：

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY="你的 LangSmith key"
LANGSMITH_PROJECT="seki-agent-local"
```

## 3. 本地启动

### 3.1 启动后端

```powershell
cd D:\seki\AI\Langchain\seki_agent\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

### 3.2 启动前端

另开一个终端：

```powershell
cd D:\seki\AI\Langchain\seki_agent\frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 4. 用户管理

### 4.1 创建或更新用户

```powershell
cd D:\seki\AI\Langchain\seki_agent\backend
.\.venv\Scripts\python.exe scripts\create_user.py demo demo123
```

脚本会打印实际写入的数据库路径。它必须和后端 `.env` 中 `SEKI_DATABASE_PATH` 一致。

### 4.2 登录

前端打开登录页，输入：

```text
用户名：demo
密码：demo123
```

## 5. 前端页面使用

- 文件管理：先上传需要翻译、解析或比较的文件。
- Agent 入口：
  - 可输入千问 API key 和火山搜索 API key，作为本次请求临时 key。
  - 可直接让 Agent 查知识库、联网搜索、找文件、创建翻译/SPI/diff 任务。
  - code agent 高风险操作会出现确认卡片。
- 文档翻译：手动选择 workspace 文件并创建翻译任务。
- SPI log 解析：选择 `.log` 文件创建解析任务。
- 版本差分：选择两个 `.tar.gz` 文件创建差分任务。
- 任务历史：查看和取消最近任务。

## 6. Docker 部署

### 6.1 准备 Docker `.env`

Docker 环境建议从模板复制：

```powershell
copy .env.example .env
```

Docker 中路径应使用 `/app/data/...`，例如：

```env
SEKI_DATA_DIR="/app/data"
SEKI_DATABASE_PATH="/app/data/db/seki_agent.db"
SEKI_WORKSPACE_DIR="/app/data/workspace"
SEKI_LEGACY_SRC_DIR="/app/backend/legacy"
```

### 6.2 构建并启动

```powershell
cd D:\seki\AI\Langchain\seki_agent
docker compose up --build -d
```

查看状态：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f backend
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

## 7. 测试和构建

后端测试：

```powershell
cd D:\seki\AI\Langchain\seki_agent
.\backend\.venv\Scripts\python.exe -m pytest
```

前端检查：

```powershell
cd D:\seki\AI\Langchain\seki_agent\frontend
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

通常是 `create_user.py` 写入的 DB 和后端读取的 DB 不一致。检查脚本输出的数据库路径，并确认 `.env` 中 `SEKI_DATABASE_PATH` 是同一个路径。

### Agent 提示缺少 API key

可以二选一：

- 在 `.env` 配置 `SEKI_RAG_API_KEY`。
- 在前端 Agent 页面输入临时千问 API key。

### 联网搜索不可用

可以二选一：

- 在 `.env` 配置 `SEKI_WEB_SEARCH_API_KEY`。
- 在前端 Agent 页面输入临时火山搜索 API key。

### Docker 前端访问不到后端

确认 `docker-compose.yml` 中前端构建参数：

```yaml
VITE_API_BASE_URL: "http://localhost:8000/api/v1"
```

如果部署到另一台机器，需要把这里改成浏览器能访问到的后端地址。
