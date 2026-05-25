# Code Agent 安全执行设计

本文档用于重新设计旧 `old/src/code_agent.py` 的代码助手能力。目标不是简单迁移 `read_file/write_file/delete_file/execute_shell` 四个工具，而是把 code agent 设计成可控、可审计、可测试、可逐步放权的本地执行助手。

## 1. 目标

Code agent 的最终目标：

- 能像工程助手一样理解任务、查看文件、编写小脚本、运行受限命令、读取结果并总结。
- 能在用户授权范围内操作项目文件，而不是获得整个系统的任意文件权限。
- 能把危险操作分级处理：安全操作直接执行，高风险操作需要确认，禁止操作直接拒绝。
- 能记录操作审计，便于排查“执行了什么、写了哪些文件、命令输出是什么”。
- 能被单元测试覆盖，不依赖真实 LLM、不依赖真实危险 shell。

非目标：

- 不做通用远程终端。
- 不让 LLM 获得无限制 shell。
- 不默认开放删除、递归移动、系统目录读写、网络下载、包安装、Git reset 等高风险操作。
- 不绕过当前用户的 workspace 隔离。

## 2. 旧实现问题

旧 `old/src/code_agent.py` 的核心能力：

- `read_file(file_path)`
- `write_file(file_path, content)`
- `delete_file(file_path)`
- `execute_shell(command)`

主要风险：

- 路径校验只用字符串前缀判断，遇到大小写、符号链接、路径规范化边界时不够稳。
- shell 命令只用少量危险字符串过滤，无法覆盖命令拼接、PowerShell/cmd 差异、重定向、管道、环境变量、下载执行等场景。
- 写文件默认覆盖，没有 diff/预览/审计。
- 删除文件直接开放，不适合作为第一阶段能力。
- 没有用户确认流程。
- 没有操作记录、命令超时策略细分、输出裁剪和敏感信息过滤。
- 所有工具直接挂给 Agent，缺少 service 层，难以独立测试和替换。

## 3. 新架构

```text
LangGraph code_agent
  |
  v
CodeAgentToolAdapter
  |
  v
CodeExecutionService
  |
  +-- PathPolicy
  +-- CommandPolicy
  +-- AuditLogger / repository
  +-- FileOperation backend
  +-- ShellExecution backend
```

边界职责：

- `CodeAgentToolAdapter`：把 LangChain/LangGraph 工具参数映射到 service，不直接操作文件或 shell。
- `CodeExecutionService`：执行真实文件和命令能力，负责权限、路径、策略、审计、输出裁剪。
- `PathPolicy`：判断路径是否在允许根目录内、是否可读、是否可写、是否是符号链接、文件大小限制。
- `CommandPolicy`：解析命令，判断是否允许、需要确认或禁止。
- `AuditLogger`：记录用户、conversation、agent、工具名、参数摘要、结果摘要、时间、状态。

## 4. 权限模型

### 4.1 允许根目录

首期只允许操作：

- 当前项目根目录：用于开发/调试本项目。
- 当前用户 workspace：用于处理用户上传文件和生成脚本结果。
- 共享 skills 目录：用于后续所有用户通用的 skills 热插拔能力，默认建议为 `data/skills`。
- 后续可通过配置增加其他只读或受限写入目录。

所有路径必须：

- 使用 `Path.resolve()` 得到绝对路径。
- 校验 resolved path 是否位于允许根目录内。
- 默认拒绝符号链接跳出允许根目录。
- 输出给用户时隐藏不必要的内部绝对路径，优先显示相对路径。

### 4.2 文件能力分级

第一阶段建议开放：

| 能力 | 默认策略 | 说明 |
| --- | --- | --- |
| `list_dir` | 允许 | 限制目录、数量、隐藏文件可配置 |
| `read_text_file` | 允许 | 限制大小，默认 1MB |
| `write_text_file` | 允许但受限 | 仅允许写入允许目录，默认不覆盖已有文件，或要求 `overwrite=true` |
| `append_text_file` | 允许但受限 | 限制大小和目标扩展名 |
| `delete_file` | 默认禁用 | 后续必须用户确认，且只允许删除 code agent 自己创建的临时文件 |
| `move/rename` | 默认禁用 | 后续再评估 |

写文件原则：

- 默认创建新文件。
- 覆盖已有文件必须显式 `overwrite=true`。
- 后续可增加“返回 diff，等待用户确认再写入”。

### 4.3 命令能力分级

命令按风险分三类：

| 等级 | 策略 | 示例 |
| --- | --- | --- |
| Allow | 可直接执行 | `python script.py`、`pytest path`、`rg pattern`、`ls/dir` |
| Confirm | 需要用户确认 | `pip install`、`npm install`、`git commit`、长耗时构建 |
| Deny | 永久拒绝 | 删除/格式化/权限修改/系统目录操作/任意下载执行/`git reset --hard` |

第一阶段只开放白名单命令：

- Python：当前虚拟环境 Python 执行工作区内脚本。
- 测试：`pytest` 指定测试文件。
- 搜索/查看：`rg`、`python -m pytest`、`npm run build`、`npm run lint` 等可配置前缀。

暂不开放：

- 任意 shell 字符串。
- 管道、重定向、命令连接符。
- `rm`、`del`、`Remove-Item`、`move`、`mv`。
- `curl|bash`、`Invoke-WebRequest` 下载执行。
- 修改系统环境、注册表、权限、服务。

## 5. 工具设计

建议 code agent 首期工具：

```text
list_dir(path, limit=100)
read_text_file(path, max_bytes=1048576)
write_text_file(path, content, overwrite=false)
run_python_script(path, args=[])
run_allowed_command(command, args=[], timeout_seconds=30)
transfer_to_main_agent()
```

不要首期暴露：

```text
delete_file
execute_shell(command: str)
```

原因：`execute_shell(command: str)` 太自由，难以可靠做安全判断。更好的方式是把命令拆成 `command + args`，并用白名单前缀匹配。

## 6. 用户确认流程

需要确认的操作不直接执行，返回结构化响应：

```json
{
  "status": "requires_confirmation",
  "operation_id": "op-id",
  "summary": "准备运行 npm install",
  "risk": "可能修改 node_modules 和 package-lock.json",
  "command_preview": "npm install",
  "expires_at": "..."
}
```

用户确认后再调用：

```text
confirm_code_operation(operation_id)
```

MVP 可以先不做确认 API，只把 Confirm 类操作拒绝并提示“该操作需要确认流程，当前尚未开放”。等只读/受限写入稳定后再加确认。

## 7. 审计记录

每次工具调用至少记录：

- `operation_id`
- `owner_username`
- `conversation_id`
- `agent_name`
- `tool_name`
- `status`: `succeeded/failed/rejected/requires_confirmation`
- `target_path` 或 `command_summary`
- `started_at` / `finished_at`
- `stdout/stderr` 摘要
- `error` 摘要

敏感信息处理：

- 不记录 API key、token、密码。
- 输出内容裁剪，避免大文件或命令输出撑爆数据库。
- 内部绝对路径可记录到审计，但返回给普通用户时优先使用相对路径。

## 8. 错误映射

所有错误统一成用户可理解信息：

- 路径越界：`该路径不在允许的工作目录内。`
- 文件过大：`文件超过当前读取限制。`
- 命令不在白名单：`该命令未开放给 code agent。`
- 命令超时：`命令执行超时，已停止等待结果。`
- 需要确认：`该操作需要用户确认，当前暂未执行。`

不要返回：

- 完整堆栈。
- API key。
- 系统敏感路径。

## 9. 分阶段落地

### 阶段 A：只读 + 安全写入 MVP

目标：

- 新增 `CodeExecutionService`。
- 支持 `list_dir/read_text_file/write_text_file`。
- 默认不开放 shell。
- 补完整单元测试：路径越界、文件大小、覆盖策略、用户隔离、审计记录。

### 阶段 B：受限脚本执行

目标：

- 支持 `run_python_script`。
- 只能运行允许目录下的脚本。
- 使用当前后端虚拟环境 Python。
- 设置 cwd、timeout、输出裁剪。
- 禁止网络下载、删除、系统目录操作。

### 阶段 C：命令白名单

目标：

- 新增 `CommandPolicy`。
- 支持白名单前缀，例如 `pytest`、`npm run lint`、`npm run build`。
- 禁止 shell control operators：管道、重定向、`&&`、`;` 等。
- 高风险命令进入确认流程。

策略判断：

- 不采用纯黑名单。命令空间太大，纯黑名单一定会漏掉危险变体。
- 采用“白名单为主、黑名单兜底”：只有明确允许的命令族可以执行；同时用黑名单拦截危险命令和 shell 控制符。

### 阶段 D：用户确认与审计 UI

目标：

- 新增 pending operation 表。
- 前端 Agent 页面展示“待确认操作”。
- 用户确认后执行。
- 支持取消 pending operation。

### 阶段 E：更智能的工程助手体验

目标：

- code agent 先规划再执行。
- 执行前读取相关文件、执行后总结变更。
- 写文件时生成 diff 摘要。
- 能根据测试失败结果自动迭代修复，但仍受命令策略限制。

## 10. 测试要求

默认测试不执行真实危险命令。

必须覆盖：

- 路径规范化和越界拒绝。
- 允许目录内读写成功。
- 大文件读取拒绝。
- 覆盖已有文件需要显式参数。
- 禁止删除。
- 命令白名单允许/拒绝。
- 命令超时。
- stdout/stderr 裁剪。
- 审计记录创建。
- Agent tool adapter 参数映射。

## 11. 推荐下一步

下一步只实现阶段 A：

- `backend/app/services/code_execution_service.py`
- `backend/tests/test_code_execution_service.py`

首批只开放：

- `list_dir`
- `read_text_file`
- `write_text_file`

暂不接 LangGraph code agent 工具，先把 service 边界和安全测试打稳。

## 12. 阶段 A 落地状态

已完成：

- 新增 `backend/app/services/code_execution_service.py`。
- 新增 `backend/tests/test_code_execution_service.py`。
- 支持 `list_dir`、`read_text_file`、`write_text_file`。
- 写文件默认不覆盖已有文件，必须显式 `overwrite=true`。
- 默认限制读取和写入 1MB，可通过配置调整。
- 默认允许读取/执行根目录为当前用户 workspace、项目根目录和共享 skills 目录，可通过配置调整。
- 默认可写工作目录为 `data/workspace/{username}`；项目根目录和共享 skills 目录用于读取/执行，不作为默认写入位置。
- 默认拒绝 `.env`、私钥、证书、数据库文件等敏感文件名或后缀。
- 每次调用都会生成内存审计记录，包含用户、会话、agent、工具名、状态、目标和时间。

仍未开放：

- 任意 `execute_shell(command)`。
- 持久化审计表。
- 前端用户确认流程。

## 13. 阶段 A 工具接入状态

已完成：

- 新增 `backend/app/services/code_agent_tools.py`。
- 新增 `backend/app/services/code_langchain_tool_adapter.py`。
- 新增 `backend/app/services/code_agent_factory.py`。
- code_agent LangGraph graph 已注册：
  - `code_list_dir`
  - `code_read_text_file`
  - `code_write_text_file`
  - `code_run_python_script`
  - `code_run_allowed_command`
  - `code_create_dir`
  - `code_delete_path`
  - `transfer_to_main_agent`
- 父级 multi-agent graph 已支持真实 code agent graph，而不是只能调用 `CodeAgentUnavailableRunner` 占位。
- 默认 runner 会创建 main agent graph + code agent graph。

仍然保持：

- 不开放任意 shell。
- 删除只对 code agent 本次运行创建的内容直接执行；其他既有内容返回 `requires_confirmation`。

## 14. 受限 Python 脚本执行状态

已完成：

- `CodeExecutionService.run_python_script(...)`。
- `code_run_python_script` LangChain tool。
- 只能运行允许根目录内已存在的 `.py` 文件。
- 工作目录固定为脚本所在目录。
- 使用当前后端 Python 解释器。
- 支持参数列表 `script_args`，不用任意 shell 字符串。
- 支持超时，默认不超过 service 配置的最大超时。
- 支持 stdout/stderr 输出裁剪。
- 记录审计。

仍然保持：

- 不支持任意 shell。
- 不支持管道、重定向、`&&`、`;` 等 shell control operators。

## 15. 删除策略状态

已完成：

- `CodeExecutionService.create_dir(...)`。
- `CodeExecutionService.delete_path(...)`。
- `code_create_dir` LangChain tool。
- `code_delete_path` LangChain tool。
- code agent 本次运行创建的文件可以直接删除。
- code agent 本次运行创建的目录可以在 `recursive=true` 时递归删除。
- code agent 本次运行创建目录下的普通文件可以直接删除。
- 既有文件或目录不会直接删除，会返回 `requires_confirmation`。

仍未完成：

- 用户确认 API。
- pending operation 持久化。
- 前端确认 UI。

关于 shell 和删除：

- 最终目标是开放，但必须按阶段开放。
- code agent 自己创建的文件/文件夹可以直接清理；其他内容必须进入确认流程。
- shell 不应提供 `execute_shell(command: str)` 这种任意字符串接口，而应先开放 `run_python_script`，再开放命令白名单，最后对高风险命令走用户确认。

## 16. 命令白名单状态

已完成：

- `CommandPolicy`。
- `CodeExecutionService.run_allowed_command(...)`。
- `code_run_allowed_command` LangChain tool。
- 命令接口为 `command + command_args`，不是任意 shell 字符串。
- 允许：
  - `git status`
  - `git diff`
  - `pytest ...`
  - `python -m pytest ...`
  - `npm run lint`
  - `npm run build`
- 拒绝：
  - 删除、移动、下载执行、权限修改等危险命令。
  - 管道、重定向、`&&`、`;`、换行等 shell 控制符。
- 进入用户确认：
  - 未在白名单中、也未命中明确黑名单的命令。
- 支持超时和 stdout/stderr 裁剪。
- 记录审计。

仍未开放：

- 任意 shell。
- 包安装类命令。
- Git 写操作。
- 用户确认后的高风险命令执行。

## 17. 人机交互确认策略

当前判断：

- 当前本地安装的 LangChain/LangGraph 版本未发现可直接稳定接入的 `HumanInTheLoopMiddleware` 类。
- LangGraph 的 interrupt 能力可以作为后续候选，但需要和 FastAPI Chat API、前端状态恢复、pending operation 持久化一起设计。
- 短期先在后端 service 层实现自己的 pending operation 边界更稳：工具返回 `requires_confirmation`，后端记录待确认操作，前端展示给用户，用户确认后再执行。

后续确认流程建议：

```text
code tool -> CodeExecutionService -> requires_confirmation
  -> PendingOperationRepository
  -> Chat API response.data.pending_operation
  -> Frontend confirmation UI
  -> POST /api/v1/code-operations/{operation_id}/confirm
  -> CodeExecutionService execute confirmed operation
```

等确认流程稳定后，再评估是否把 LangGraph interrupt 接入同一套 pending operation 存储。

## 18. Pending Operation 后端边界状态

本轮已落地后端 pending operation MVP：

- 新增 `code_pending_operations` 表，由 `CodeOperationRepository` 初始化。
- 新增 `CodeOperationService`，负责创建、查询、取消、确认待确认操作。
- 新增 `/api/v1/code-operations` API：
  - `GET /api/v1/code-operations`
  - `GET /api/v1/code-operations/{operation_id}`
  - `POST /api/v1/code-operations/{operation_id}/confirm`
  - `POST /api/v1/code-operations/{operation_id}/cancel`
- `AgentService` 会在 runner 返回 `data.requires_confirmation=true` 时创建 pending operation，并把 `pending_operation` 放入 Chat API 响应。
- 已支持确认执行 `delete_path`：非 code agent 本轮创建的既有文件/目录，必须先进入 pending，用户确认后才会删除。
- 未知 shell 命令可进入 pending，但确认后暂不真实执行，当前返回“确认后执行未知命令的策略尚未开放”。后续需要单独设计确认后命令执行边界。

状态语义：

```text
pending -> executed
pending -> failed
pending -> cancelled
pending -> expired
```

对话状态策略：

- 不让原始 Chat HTTP 请求一直阻塞等待用户确认。
- 本轮 agent 对话直接结束，并返回结构化 `pending_operation`。
- 前端确认/取消是新的 API 调用。
- 确认执行完成后，后端会向同一个 conversation 追加一条 assistant 消息，用于展示执行结果。
- 后续如果接入 LangGraph interrupt/resume，可以复用同一张 pending operation 表作为持久化确认边界。

## 19. Pending Operation 前端闭环

本轮已在 Agent 入口页面接入待确认操作：

- 新增前端类型 `CodeOperation` 和 API client。
- Agent 对话返回 `data.pending_operation` 时，会在当前 assistant 消息下展示待确认卡片。
- 待确认卡片展示操作类型、状态、目标和执行结果。
- 用户可在 Agent 页面点击“确认执行”或“取消”。
- 确认/取消后更新同一条消息里的 pending operation 状态。
- Agent 页面提供“刷新待确认”，可按当前 conversation 拉取仍处于 `pending` 的操作。

该入口仍然属于 Agent 主线：前端只负责把 agent 的暂停点展示给用户，不把 code agent 做成独立页面，也不绕过后端 service/审计边界。

## 20. 工具级 Pending 与配置化命令策略

本轮继续完成两项 Agent 主线能力：

- `code_delete_path` 和 `code_run_allowed_command` 工具在返回 `requires_confirmation` 时，会当场创建 pending operation。
- 工具结果文本会包含 `pending_operation_id`，即使 LLM 最终回答没有保留结构化字段，前端也能通过当前 conversation 刷新待确认列表找回。
- `AgentService` 出口处的 `data.requires_confirmation` 兜底仍然保留，用于非 LangGraph/fake runner 或后续其他 runner。

命令策略新增配置：

```env
SEKI_CODE_AGENT_ALLOWED_COMMAND_PREFIXES='["ruff check","npm test"]'
SEKI_CODE_AGENT_CONFIRMED_COMMAND_PREFIXES='["python --version"]'
```

语义：

- 内置白名单仍然直接执行，如 `git status/diff`、`pytest`、`python -m pytest`、`npm run lint/build`。
- `SEKI_CODE_AGENT_ALLOWED_COMMAND_PREFIXES` 命中的命令直接执行。
- `SEKI_CODE_AGENT_CONFIRMED_COMMAND_PREFIXES` 命中的命令先进入 pending，用户确认后执行。
- 其他未知命令可以进入 pending，但确认后仍不会执行，除非它匹配 confirmed prefix。
- 明确危险命令和 shell 控制符仍直接拒绝。

## 21. Agent 入口本地测试方式

Agent 入口默认运行时已收敛为 LangGraph，不再通过环境变量切换到 rule runner，也不再通过关键词猜测 code_agent handoff。

- 前端关闭“使用知识库 / RAG”时，仍由 LangGraph Agent 和系统 prompt 判断是否普通聊天。
- API key 统一使用后端环境变量配置，前端不再传入临时 key。
- `RuleBasedAgentRunner` 仅保留为单元测试/显式注入调试构件，不作为本地运行入口。
- code_agent 交接应由 LangGraph Agent 通过 `transfer_to_code_agent` 工具决定。
