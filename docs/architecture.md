# Seki Agent 目标架构设计

## 1. 架构目标

本阶段目标是将当前脚本式/Streamlit 原型改造为前后端分离、模块清晰、可测试、可部署的工程项目。

已确认技术栈：

- 前端：React + Vite + TypeScript。
- 后端：FastAPI。
- 部署：Docker Compose + 本机。
- 登录：内部账号密码。
- 用户规模：公司多部门内部用户，约 50 人。
- Streamlit：不保留，后续迁移到正式前后端架构。

## 2. 总体架构

```text
Browser
  |
  | HTTP / SSE
  v
React Frontend
  |
  | REST API
  v
FastAPI Backend
  |
  +-- auth          用户、登录、密码校验
  +-- files         文件上传、下载、删除、workspace 隔离
  +-- rag           知识库问答、检索、重排、答案生成
  +-- translation   文档翻译
  +-- spi           SPI log 解析
  +-- diff          版本差分比较
  +-- agents        LangGraph Agent 编排
  +-- tasks         后台任务抽象
  +-- storage       数据库、文件系统、向量库适配
  |
  +-- SQLite / PostgreSQL-compatible repository layer
  +-- Local File Storage
  +-- Chroma Vector DB
  +-- External LLM APIs
```

## 3. 首期架构策略

首期采用“模块化单体”。

原因：

- 当前用户规模约 50 人，不需要一开始拆微服务。
- 业务边界还在沉淀，模块化单体更容易重构和调试。
- Docker Compose 本机部署更适合简单拓扑。
- 后续如果某些能力负载变重，可以按模块拆分服务。

## 3.1 Agent 与前端双入口策略

最终产品同时保留两类使用入口：

- Agent 对话入口：用户通过自然语言提出目标，由后端 `agents` 模块判断是否调用 RAG、文件翻译、SPI 解析、版本差分、文件管理等工具。
- 前端手动入口：用户也可以直接在页面点击按钮使用文件、翻译、SPI、diff 等能力。

两类入口必须复用同一套后端 service 能力：

```text
React Pages  --->  FastAPI Routers  --->  services/files|translation|spi|diff|rag
Agent Tools  --->  Agent Tool Layer  --->  services/files|translation|spi|diff|rag
```

原则：

- 前端页面不是 Agent 的替代品，而是工程化后的可视化入口和调试入口。
- Agent 工具不直接读写散落的本地路径，不重复实现业务逻辑，应调用后端 service 或明确的 tool adapter。
- 会话状态必须按 `owner_username + conversation_id` 隔离，禁止使用全局闭包变量保存多用户上下文。
- 长耗时工具调用继续走任务化接口，Agent 只负责创建任务、查询状态和组织结果。
- 对每个工具能力，至少保留 service 单元测试；Agent 工具层通过 mock service 测试路由和参数映射。

## 4. 后端目录结构建议

```text
backend/
  app/
    main.py
    api/
      router.py
      v1/
        auth.py
        files.py
        chat.py
        translation.py
        spi.py
        diff.py
        tasks.py
        health.py
    core/
      config.py
      logging.py
      security.py
      exceptions.py
    schemas/
      auth.py
      files.py
      chat.py
      tasks.py
      common.py
    services/
      auth_service.py
      file_service.py
      rag_service.py
      translation_service.py
      spi_service.py
      diff_service.py
      agent_service.py
      task_service.py
    repositories/
      user_repository.py
      task_repository.py
      file_repository.py
    storage/
      local_file_storage.py
      vector_store.py
    integrations/
      llm_clients.py
      rerank_clients.py
    tests/
```

## 5. 前端目录结构建议

```text
frontend/
  src/
    app/
    pages/
      LoginPage.tsx
      ChatPage.tsx
      FilesPage.tsx
      TranslationPage.tsx
      SpiPage.tsx
      DiffPage.tsx
    components/
    api/
    hooks/
    stores/
    types/
```

## 6. 模块边界

### 6.1 auth

职责：

- 内部账号密码登录。
- 密码哈希校验。
- 登录态/JWT 管理。
- 当前用户识别。

不负责：

- 文件权限业务。
- Agent 会话逻辑。

### 6.2 files

职责：

- 用户 workspace 文件上传。
- 文件列表、下载、删除。
- 文件路径安全校验。
- 文件元数据登记。

不负责：

- 文档翻译。
- 知识库入库。
- SPI log 解析。

### 6.3 rag

职责：

- 知识库检索。
- Rerank。
- Prompt 组装。
- LLM 问答。
- 引用来源处理。

不负责：

- 用户登录。
- 文件上传 API。
- 前端展示。

### 6.4 translation

职责：

- 文档翻译业务编排。
- 调用现有翻译模块。
- 生成翻译结果文件。
- 返回任务状态。

### 6.5 spi

职责：

- SPI log 解析。
- 标准化解析输入输出。
- 支持任务化调用。

### 6.6 diff

职责：

- 版本差分比较。
- 标准化差分输入、输出、错误。
- 后续可扩展可视化结果格式。

### 6.7 agents

职责：

- LangGraph 编排。
- Agent 会话状态。
- Agent 工具注册。
- 将文件、翻译、SPI、diff、RAG 等 service 能力暴露为 Agent 可调用工具。
- 将自然语言意图路由到 RAG、工具调用、普通回答或后续代码助手。

要求：

- 会话状态必须按用户和会话隔离。
- 不使用全局闭包变量保存多用户上下文。
- Agent 编排层不直接实现文件解析、翻译、差分等业务逻辑。
- 工具调用失败时返回标准化错误，避免泄露 API Key、路径和内部异常细节。

## 7. 数据与存储

首期建议：

- 用户与任务元数据：SQLite。
- 文件存储：本地目录。
- 向量库：保留 Chroma。
- 配置：`.env` + `pydantic-settings`。

路径建议：

```text
data/
  db/
  uploads/
  workspace/
  translation/
  spi/
  diff/
  vector_db/
  parent_store/
```

原则：

- 运行时数据不要放在源码目录。
- 所有路径通过配置集中管理。
- 用户文件路径必须做安全校验，禁止路径穿越。

## 8. 任务处理

首期可以先实现进程内任务管理接口，保留后续迁移到 Celery/RQ 的边界。

任务化能力：

- 文档翻译。
- SPI log 解析。
- 版本差分比较。
- 后续知识库入库。

任务状态：

- `pending`
- `running`
- `succeeded`
- `failed`
- `cancelled`

后续当并发任务变多时，引入：

- Redis。
- Celery 或 RQ。
- 独立 worker 容器。

## 9. 并发设计

首期重点：

- FastAPI 接口保持无状态。
- 用户会话、任务状态、文件元数据落库。
- Agent 会话按 `user_id + conversation_id` 隔离。
- LLM 调用设置超时、重试和错误映射。
- 长任务走任务接口，不阻塞普通请求。

## 10. 安全设计

首期要求：

- 密码使用 PBKDF2、bcrypt 或 argon2 哈希。
- 登录后使用 token。
- API Key 不返回前端。
- 文件访问必须校验当前用户。
- 上传文件限制大小和扩展名。
- 日志不打印密码、token、API Key。

## 11. 测试设计

测试分层：

- 单元测试：service、repository、纯函数工具。
- 接口测试：FastAPI router。
- 集成测试：RAG/翻译/SPI/diff 的最小链路。
- Mock 测试：外部 LLM、rerank、embedding API。

首期测试重点：

- 登录成功/失败。
- 文件路径隔离。
- 文件上传下载删除。
- 任务状态流转。
- SPI log 解析输入输出。
- diff 结果标准化。
- RAG service 在 mock LLM 下可运行。

## 12. 部署设计

首期 Docker Compose 服务建议：

```text
backend
frontend
```

后续可扩展：

```text
backend
frontend
redis
worker
qdrant
postgres
minio
```

首期本机部署原则：

- 容器挂载 `data/` 作为持久化目录。
- `.env` 管理密钥和路径。
- 后端提供 `/api/v1/health` 健康检查。
- 前端通过环境变量配置 API Base URL。

## 13. 迁移策略

建议迁移顺序：

1. 新建 FastAPI 后端骨架。
2. 实现配置、日志、异常、健康检查。
3. 迁移用户认证。
4. 迁移文件管理。
5. 迁移 diff 能力。
6. 迁移 SPI log 解析。
7. 迁移文档翻译。
8. 迁移知识库问答和 Agent。
9. 新建 React 前端并逐步对接 API。
10. 完善 Docker Compose 和测试。
