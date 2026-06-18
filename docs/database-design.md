# Seki Agent 数据库设计文档

> 数据库类型：PostgreSQL  
> 最后更新：2026-06-17  
> 表数量：11 张  
> 字符集：UTF-8

---

## 目录

1. [总览](#总览)
2. [users — 用户表](#1-users--用户表)
3. [conversations — 会话表](#2-conversations--会话表)
4. [chat_messages — 聊天消息表](#3-chat_messages--聊天消息表)
5. [files — 文件表](#4-files--文件表)
6. [translation_tasks — 翻译任务表](#5-translation_tasks--翻译任务表)
7. [spi_tasks — SPI 解析任务表](#6-spi_tasks--spi-解析任务表)
8. [diff_tasks — 版本差分任务表](#7-diff_tasks--版本差分任务表)
9. [code_pending_operations — 代码待确认操作表](#8-code_pending_operations--代码待确认操作表)
10. [code_audit_records — 代码操作审计表](#9-code_audit_records--代码操作审计表)
11. [agent_trace_runs — Agent 追踪运行表](#10-agent_trace_runs--agent-追踪运行表)
12. [agent_trace_events — Agent 追踪事件表](#11-agent_trace_events--agent-追踪事件表)

---

## 总览

### ER 关系图

```
users (username)
  │
  ├──< conversations (owner_username)
  │       │
  │       ├──< chat_messages (conversation_id)
  │       │
  │       ├──< code_pending_operations (conversation_id)
  │       │
  │       └──< code_audit_records (conversation_id)
  │
  ├──< files (owner_username)
  │       │
  │       ├──< translation_tasks (file_id)
  │       ├──< spi_tasks (file_id)
  │       └──< diff_tasks (left_file_id / right_file_id)
  │
  ├──< agent_trace_runs (owner_username + conversation_id)
  │       │
  │       └──< agent_trace_events (run_id)
  │
  └──< (各任务表的 owner_username)
```

### 表分类

| 分类 | 表名 | 说明 |
|------|------|------|
| 用户认证 | `users` | 内部账号密码管理 |
| 对话系统 | `conversations`, `chat_messages` | Agent 会话和消息持久化 |
| 文件管理 | `files` | 用户上传文件元数据 |
| 业务任务 | `translation_tasks`, `spi_tasks`, `diff_tasks` | 翻译/SPI/Diff 异步任务 |
| 代码助手 | `code_pending_operations`, `code_audit_records` | Code Agent 操作确认和审计 |
| 可观测性 | `agent_trace_runs`, `agent_trace_events` | Agent 运行追踪和工具事件 |

---

## 1. users — 用户表

**作用**：存储内部账号信息，用于登录认证和权限控制。密码以 bcrypt 哈希存储，支持管理员标记。

**Repository**：`backend/app/repositories/user_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `username` | TEXT | ✅ | ✅ | — | 用户名，唯一标识 |
| `password_hash` | TEXT | | ✅ | — | bcrypt 哈希后的密码 |
| `is_admin` | BOOLEAN | | ✅ | `FALSE` | 是否为管理员账号 |
| `created_at` | TEXT | | ✅ | — | 创建时间（ISO 8601 UTC） |
| `updated_at` | TEXT | | ✅ | — | 最后更新时间（ISO 8601 UTC） |

**索引**：无额外索引（主键 `username` 自带唯一索引）。

---

## 2. conversations — 会话表

**作用**：记录每个用户的 Agent 对话会话。每个会话有独立的 `active_agent` 标记当前活跃的 Agent（主 Agent 或 Code Agent），支持多 Agent 上下文切换。`agent_summaries` 存储历史消息摘要，用于长会话的上下文窗口压缩。

**Repository**：`backend/app/repositories/chat_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 会话 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名，关联 `users.username` |
| `active_agent` | TEXT | | ✅ | `'main_agent'` | 当前活跃 Agent 名称（`main_agent` 或 `code_agent`） |
| `agent_summaries` | TEXT | | ✅ | `'{}'` | JSON 字符串，按 Agent 名称存储历史消息摘要，格式：`{"main_agent": {"text": "...", "covered_message_count": N}, "code_agent": {...}}` |
| `total_tokens` | BIGINT | | ✅ | `0` | 会话累计消耗的 token 总数 |
| `token_limit_multiplier` | INTEGER | | ✅ | `1` | token 限额倍数，达到 `base_limit × multiplier` 时需要用户确认才能继续 |
| `created_at` | TEXT | | ✅ | — | 创建时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_conversations_owner_username` | `owner_username` | 按用户查询会话列表 |

---

## 3. chat_messages — 聊天消息表

**作用**：持久化每轮对话中的所有消息，包括用户输入、Agent 回复、工具调用（tool_calls）和工具返回结果。按 `agent_name` 隔离主 Agent 和 Code Agent 的消息，确保上下文不串。

**Repository**：`backend/app/repositories/chat_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 消息 ID（UUID hex，32 位） |
| `conversation_id` | TEXT | | ✅ | — | 所属会话 ID，外键关联 `conversations.id` |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `role` | TEXT | | ✅ | — | 消息角色：`user`（用户输入）、`assistant`（Agent 回复）、`tool`（工具调用/返回） |
| `content` | TEXT | | ✅ | — | 消息文本内容 |
| `agent_name` | TEXT | | ✅ | `'main_agent'` | 产生此消息的 Agent 名称（`main_agent` 或 `code_agent`） |
| `metadata` | TEXT | | ✅ | `'{}'` | JSON 字符串，存储额外元数据，如 `{"tool_calls": [...]}` |
| `created_at` | TEXT | | ✅ | — | 创建时间（ISO 8601 UTC） |

**外键**：`conversation_id` → `conversations(id)`

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_chat_messages_conversation_id` | `conversation_id` | 按会话查询消息 |
| `idx_chat_messages_conversation_agent` | `conversation_id`, `agent_name` | 按会话 + Agent 查询隔离消息 |

---

## 4. files — 文件表

**作用**：记录用户上传文件的元数据。文件实际存储在磁盘 `data/workspace/{owner_username}/` 目录下，此表只保存文件名、路径和大小等信息。Code Agent 创建或删除文件后，`FileService.sync_workspace_files()` 会同步更新此表。

**Repository**：`backend/app/repositories/file_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 文件 ID（UUID hex，32 位），其他任务表通过此 ID 引用文件 |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `filename` | TEXT | | ✅ | — | 原始文件名（经过安全清洗后的名称） |
| `storage_path` | TEXT | | ✅ | — | 磁盘存储绝对路径，格式：`data/workspace/{owner}/{file_id}_{filename}` |
| `size` | INTEGER | | ✅ | — | 文件大小（字节） |
| `created_at` | TEXT | | ✅ | — | 上传时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_files_owner_username` | `owner_username` | 按用户查询文件列表 |

---

## 5. translation_tasks — 翻译任务表

**作用**：记录文档翻译异步任务的状态和结果。支持 Excel、Word、PPT 格式翻译，翻译结果生成为新文件并通过 `result_file_id` 关联到 `files` 表。

**Repository**：`backend/app/repositories/translation_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `task_id` | TEXT | ✅ | ✅ | — | 任务 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `file_id` | TEXT | | ✅ | — | 待翻译文件 ID，关联 `files.id` |
| `target_language` | TEXT | | ✅ | — | 目标语言（如 `日语`、`英语`、`中文`） |
| `status` | TEXT | | ✅ | — | 任务状态：`pending`（等待中）、`running`（执行中）、`succeeded`（成功）、`failed`（失败） |
| `result_file_id` | TEXT | | | — | 翻译结果文件 ID，关联 `files.id`，翻译完成后写入 |
| `error` | TEXT | | | — | 失败时的错误信息 |
| `created_at` | TEXT | | ✅ | — | 任务创建时间（ISO 8601 UTC） |
| `updated_at` | TEXT | | ✅ | — | 最后更新时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_translation_tasks_owner_username` | `owner_username` | 按用户查询翻译任务 |

---

## 6. spi_tasks — SPI 解析任务表

**作用**：记录 SPI 日志解析异步任务的状态和结果。将 `.log` 文件解析为结构化 Excel 输出。

**Repository**：`backend/app/repositories/spi_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `task_id` | TEXT | ✅ | ✅ | — | 任务 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `file_id` | TEXT | | ✅ | — | 待解析的 SPI 日志文件 ID（JSON 数组字符串，支持多文件），关联 `files.id` |
| `status` | TEXT | | ✅ | — | 任务状态：`pending`、`running`、`succeeded`、`failed` |
| `result_file_id` | TEXT | | | — | 解析结果文件 ID，关联 `files.id` |
| `error` | TEXT | | | — | 失败时的错误信息 |
| `created_at` | TEXT | | ✅ | — | 任务创建时间（ISO 8601 UTC） |
| `updated_at` | TEXT | | ✅ | — | 最后更新时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_spi_tasks_owner_username` | `owner_username` | 按用户查询 SPI 任务 |

---

## 7. diff_tasks — 版本差分任务表

**作用**：记录版本包差分比较异步任务的状态和结果。比较两个 `.tar.gz` 版本压缩包的差异，生成统一 diff 文本。

**Repository**：`backend/app/repositories/diff_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `task_id` | TEXT | ✅ | ✅ | — | 任务 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `left_file_id` | TEXT | | ✅ | — | 旧版本文件 ID，关联 `files.id` |
| `right_file_id` | TEXT | | ✅ | — | 新版本文件 ID，关联 `files.id` |
| `status` | TEXT | | ✅ | — | 任务状态：`pending`、`running`、`succeeded`、`failed` |
| `result_text` | TEXT | | | — | 差分结果文本（统一 diff 格式） |
| `result_file_id` | TEXT | | | — | 差分结果文件 ID（如果结果保存为文件），关联 `files.id` |
| `error` | TEXT | | | — | 失败时的错误信息 |
| `created_at` | TEXT | | ✅ | — | 任务创建时间（ISO 8601 UTC） |
| `updated_at` | TEXT | | ✅ | — | 最后更新时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_diff_tasks_owner_username` | `owner_username` | 按用户查询差分任务 |

---

## 8. code_pending_operations — 代码待确认操作表

**作用**：存储 Code Agent 需要用户确认才能执行的操作（如覆盖已有文件）。当 Code Agent 尝试覆盖一个既有文件时，系统会生成 diff 预览并创建一条 pending 记录，等待用户在前端确认后才真正执行。

**Repository**：`backend/app/repositories/code_operation_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 操作 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `conversation_id` | TEXT | | ✅ | — | 所属会话 ID，关联 `conversations.id` |
| `agent_name` | TEXT | | ✅ | — | 发起操作的 Agent 名称（通常为 `code_agent`） |
| `operation_type` | TEXT | | ✅ | — | 操作类型，如 `write_text_file`、`delete_path`、`run_allowed_command` |
| `payload_json` | TEXT | | ✅ | — | JSON 字符串，存储操作参数（如文件路径、内容、diff 预览等） |
| `status` | TEXT | | ✅ | — | 操作状态：`pending`（待确认）、`confirmed`（已确认）、`rejected`（已拒绝）、`expired`（已过期） |
| `result_json` | TEXT | | | — | JSON 字符串，确认/拒绝后的执行结果 |
| `created_at` | TEXT | | ✅ | — | 创建时间（ISO 8601 UTC） |
| `updated_at` | TEXT | | ✅ | — | 最后更新时间（ISO 8601 UTC） |
| `expires_at` | TEXT | | ✅ | — | 过期时间（ISO 8601 UTC），超时未确认自动标记为 expired |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_code_pending_operations_owner_status` | `owner_username`, `status` | 按用户 + 状态查询待确认操作 |
| `idx_code_pending_operations_conversation` | `owner_username`, `conversation_id` | 按用户 + 会话查询 |

---

## 9. code_audit_records — 代码操作审计表

**作用**：记录 Code Agent 所有操作的审计日志，包括文件读写、目录操作、脚本执行和命令运行。用于安全审计和操作回溯。

**Repository**：`backend/app/repositories/code_audit_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 记录 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `conversation_id` | TEXT | | ✅ | — | 所属会话 ID |
| `agent_name` | TEXT | | ✅ | — | 执行操作的 Agent 名称 |
| `tool_name` | TEXT | | ✅ | — | 调用的工具名称，如 `code_write_text_file`、`code_list_dir`、`code_run_python_script` |
| `status` | TEXT | | ✅ | — | 操作结果：`succeeded`（成功）、`failed`（失败）、`rejected`（被安全策略拒绝） |
| `target` | TEXT | | ✅ | — | 操作目标路径（显示路径，非绝对路径） |
| `message` | TEXT | | ✅ | — | 操作结果描述信息 |
| `detail_json` | TEXT | | | — | JSON 字符串，存储操作详细数据（如文件内容、命令输出、returncode 等） |
| `started_at` | TEXT | | ✅ | — | 操作开始时间（ISO 8601 UTC） |
| `finished_at` | TEXT | | ✅ | — | 操作结束时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_code_audit_records_owner_time` | `owner_username`, `finished_at` | 按用户 + 时间查询审计记录 |
| `idx_code_audit_records_conversation` | `owner_username`, `conversation_id` | 按用户 + 会话查询 |

---

## 10. agent_trace_runs — Agent 追踪运行表

**作用**：记录每次 Agent 调用的运行信息，包括输入输出预览、token 消耗、执行时长和状态。用于可观测性和调试，帮助追踪 Agent 的行为和性能。

**Repository**：`backend/app/repositories/agent_trace_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 运行 ID（UUID hex，32 位） |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `conversation_id` | TEXT | | ✅ | — | 所属会话 ID |
| `agent_name` | TEXT | | ✅ | — | 执行的 Agent 名称（`main_agent` 或 `code_agent`） |
| `status` | TEXT | | ✅ | — | 运行状态：`running`（运行中）、`succeeded`（成功）、`failed`（失败）、`cancelled`（用户取消） |
| `input_preview` | TEXT | | ✅ | `''` | 用户输入消息预览（截断后的文本） |
| `answer_preview` | TEXT | | ✅ | `''` | Agent 最终回答预览 |
| `error` | TEXT | | | — | 失败时的错误信息 |
| `input_tokens` | INTEGER | | ✅ | `0` | 本次运行的输入 token 数 |
| `output_tokens` | INTEGER | | ✅ | `0` | 本次运行的输出 token 数 |
| `total_tokens` | INTEGER | | ✅ | `0` | 本次运行的总 token 数（input + output） |
| `started_at` | TEXT | | ✅ | — | 运行开始时间（ISO 8601 UTC） |
| `finished_at` | TEXT | | | — | 运行结束时间（ISO 8601 UTC） |
| `duration_ms` | INTEGER | | | — | 运行耗时（毫秒） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_agent_trace_runs_owner_time` | `owner_username`, `started_at` | 按用户 + 时间查询运行记录 |
| `idx_agent_trace_runs_conversation` | `owner_username`, `conversation_id` | 按用户 + 会话查询 |

---

## 11. agent_trace_events — Agent 追踪事件表

**作用**：记录每次 Agent 运行中的工具调用事件，包括工具名称、执行状态、耗时和输出预览。与 `agent_trace_runs` 配合，提供完整的 Agent 执行链路追踪。

**Repository**：`backend/app/repositories/agent_trace_repository.py`

| 列名 | 类型 | 主键 | 必须 | 默认值 | 说明 |
|------|------|:----:|:----:|--------|------|
| `id` | TEXT | ✅ | ✅ | — | 事件 ID（UUID hex，32 位） |
| `run_id` | TEXT | | ✅ | — | 所属运行 ID，关联 `agent_trace_runs.id` |
| `owner_username` | TEXT | | ✅ | — | 所属用户名 |
| `seq` | INTEGER | | ✅ | — | 事件序号（同一次运行内递增） |
| `event_type` | TEXT | | ✅ | — | 事件类型：`tool`（工具调用）、`model`（模型调用） |
| `name` | TEXT | | ✅ | — | 事件名称，如工具名 `rag`、`translation` 或模型名 `qwen3.7-max` |
| `status` | TEXT | | ✅ | — | 事件状态：`succeeded`（成功）、`failed`（失败） |
| `preview` | TEXT | | ✅ | `''` | 事件输出预览（截断后的文本） |
| `error` | TEXT | | | — | 失败时的错误信息 |
| `input_tokens` | INTEGER | | | — | 输入 token 数（仅 model 类型事件） |
| `output_tokens` | INTEGER | | | — | 输出 token 数（仅 model 类型事件） |
| `duration_ms` | INTEGER | | | — | 事件耗时（毫秒） |
| `created_at` | TEXT | | ✅ | — | 事件创建时间（ISO 8601 UTC） |

**索引**：

| 索引名 | 列 | 说明 |
|--------|-----|------|
| `idx_agent_trace_events_run` | `run_id`, `seq` | 按运行 ID + 序号查询事件 |

---

## 附录：状态枚举值说明

### 任务状态（translation_tasks / spi_tasks / diff_tasks）

| 状态值 | 说明 |
|--------|------|
| `pending` | 任务已创建，等待执行 |
| `running` | 任务正在后台执行 |
| `succeeded` | 任务执行成功 |
| `failed` | 任务执行失败 |

### 待确认操作状态（code_pending_operations）

| 状态值 | 说明 |
|--------|------|
| `pending` | 等待用户确认 |
| `confirmed` | 用户已确认，操作已执行 |
| `rejected` | 用户已拒绝 |
| `expired` | 超时未确认，自动过期 |

### Agent 运行状态（agent_trace_runs）

| 状态值 | 说明 |
|--------|------|
| `running` | Agent 正在执行 |
| `succeeded` | Agent 执行成功 |
| `failed` | Agent 执行失败 |
| `cancelled` | 用户主动取消（前端停止按钮） |

### 代码审计操作状态（code_audit_records）

| 状态值 | 说明 |
|--------|------|
| `succeeded` | 操作成功执行 |
| `failed` | 操作执行失败 |
| `rejected` | 被安全策略拒绝（路径越界、敏感文件、危险命令等） |

### 消息角色（chat_messages.role）

| 角色值 | 说明 |
|--------|------|
| `user` | 用户输入的消息 |
| `assistant` | Agent 生成的回复 |
| `tool` | 工具调用请求或工具返回结果 |
