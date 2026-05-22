# 当前实现状态总览

本文基于当前代码整理，不按历史对话时间线展开。旧的 `refactor-roadmap.md` 仍可作为迭代记录参考，当前后续规划以本文为准。

## 已实现

### 工程骨架

- 后端采用 FastAPI 模块化单体，入口为 `backend/app/main.py`。
- 前端采用 React + Vite + TypeScript，入口为 `frontend/src/main.tsx`。
- 后端分层为 API router、schema、service、repository、core 配置/安全模块。
- SQLite 作为当前开发期数据库，文件存储使用本地 `data/workspace`。
- Docker Compose 已包含 backend/frontend 两个服务。

### 用户与权限

- 支持内部账号密码登录。
- 支持 JWT Bearer 认证。
- 文件、任务、对话、code pending operation 均按 `owner_username` 隔离。
- 提供 `backend/scripts/create_user.py` 创建/更新本地用户。

### 文件管理

- 当前用户可上传、列出、下载、删除 workspace 文件。
- 文件名保留中文，仅清理 Windows 非法字符。
- 单文件上传默认限制 600MB。

### 业务工具

- 文档翻译：支持 `.pptx`、`.xlsx`、`.docx`，复用 legacy 翻译逻辑。
- SPI log 解析：支持单个或多个 `.log` 合并解析，输出 Excel。
- 版本差分：支持两个 `.tar.gz` 版本包差分，复用 legacy shell 脚本。
- 统一任务历史：可聚合查看 translation/SPI/diff 任务。
- 任务取消：pending/running 状态支持协作式取消。

### Agent 入口

- Chat API 已统一作为 Agent 对话入口。
- 默认运行时已收敛为 LangGraph runner，不再通过环境变量切换 rule/graph。
- `RuleBasedAgentRunner` 仅保留为单元测试/显式注入调试构件。
- Agent runner 会携带当前 conversation 最近 20 条 user/assistant 历史。
- 系统 prompt 已包含 SIS/本田/TSU/seki 开发者身份设定。
- 支持前端临时千问 API key 和火山搜索 API key，临时 key 不写入聊天记录。
- Chat SSE 接口已实现，前端可增量展示 assistant 回复。
- 当前 SSE 是接口层分片，真实 token 级流式仍待做。

### Agent 工具

- RAG 工具：回答公司业务/知识库问题。
- web_search 工具：接回旧版火山/Feedcoop 兼容搜索 provider。
- file_lookup 工具：按当前用户 workspace 文件名/后缀查找 file_id。
- translation/SPI/diff 工具：调用对应 service 创建任务。
- code_agent handoff：主 Agent 可通过 `transfer_to_code_agent` 交接到 code agent。

### Code Agent

- 已有独立 code agent graph 和工具适配层。
- 文件能力：列目录、读小文本、写小文本、创建目录。
- 受限执行：可运行允许目录内 Python 脚本，可执行白名单命令。
- 删除策略：本轮 code agent 创建的内容可直接清理；既有内容需要 pending operation。
- pending operation 后端和前端确认 UI 已接入。
- 任意 shell 字符串和高危命令仍未开放。

### 前端页面

- 登录页。
- Agent 入口页。
- 文件管理页。
- 文档翻译页。
- SPI log 解析页。
- 版本差分比较页。
- 任务历史页。
- Agent 聊天区域已改为内部滚动。

### 可观测性

- 推荐使用 LangSmith 原生环境变量追踪 LangChain/LangGraph 链路：
  - `LANGSMITH_TRACING=true`
  - `LANGSMITH_API_KEY=...`
  - `LANGSMITH_PROJECT=...`

## 待实现

### Agent 主线

- 真正 token 级流式输出：扩展 `AgentRunner` streaming 协议并接 LangGraph/ChatOpenAI 原生 stream。
- 系统化验证 `file_lookup -> translation/SPI/diff` 在真实 LangGraph 中的稳定性。
- 更强文件选择：支持前端“当前选中文件上下文”传给 Agent，降低模型查错文件概率。
- 长上下文摘要：接入可测试的 conversation summarization 策略。
- 更完整的工具调用可视化：展示工具开始、工具结果、错误、耗时。

### Web Search

- 火山搜索 provider 已可用，但仍需补配额、缓存、审计记录和更完整错误映射。
- 可评估是否增加其他搜索 provider，但不建议在没有需求时提前抽象过度。

### Code Agent

- 持久化审计表：当前 `CodeExecutionService` 的部分审计仍偏内存/返回值。
- 确认后命令执行策略需要继续收紧并可配置。
- 写文件前 diff 预览和用户确认。
- code agent 自我迭代修复流程：读文件、改文件、跑测试、总结变更。

### 并发与生产化

- 当前已有本机线程池执行器；生产建议继续评估 Redis + Celery/RQ。
- SQLite 后续应迁移 PostgreSQL。
- 本地文件存储后续可迁移 MinIO/对象存储。
- legacy Chroma/向量库后续可迁移 Qdrant 等服务化向量库。
- 增加结构化日志、健康检查细分、指标监控、备份恢复文档。

### 文档和测试

- 继续补真实 LangGraph live smoke 测试。
- 为关键业务工具增加更多边界输入测试。
- 当前文件结构和使用说明见：
  - `docs/file-structure.md`
  - `docs/user-guide.md`
