# Seki Agent API 设计草案

本文档是首期 API 草案，用于指导后续 FastAPI 后端实现。字段和错误码可在落地时继续细化。

统一前缀：

```text
/api/v1
```

## 1. 通用约定

### 1.1 响应格式

成功响应可以直接返回业务对象。

错误响应：

```json
{
  "code": "AUTH_INVALID_CREDENTIALS",
  "message": "用户名或密码错误",
  "details": {}
}
```

### 1.2 认证

除登录接口、健康检查外，其余接口默认需要认证。

认证方式：

```text
Authorization: Bearer <token>
```

## 2. 健康检查

### GET /health

用途：检查后端服务是否运行。

响应：

```json
{
  "status": "ok"
}
```

## 3. 认证

### POST /auth/login

用途：内部账号密码登录。

请求：

```json
{
  "username": "user1",
  "password": "password"
}
```

响应：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user": {
    "id": "user1",
    "username": "user1"
  }
}
```

### GET /auth/me

用途：获取当前登录用户。

响应：

```json
{
  "id": "user1",
  "username": "user1"
}
```

## 4. 文件管理

### GET /files

用途：列出当前用户 workspace 文件。

响应：

```json
{
  "items": [
    {
      "id": "file-id",
      "filename": "example.docx",
      "size": 1024,
      "created_at": "2026-05-18T10:00:00Z"
    }
  ]
}
```

### POST /files

用途：上传文件到当前用户 workspace。

限制：

- 首期单文件最大 600MB。
- 后端流式保存文件，避免一次性读入内存。

请求：

```text
multipart/form-data
file=<binary>
```

响应：

```json
{
  "id": "file-id",
  "filename": "example.docx",
  "size": 1024
}
```

### GET /files/{file_id}/download

用途：下载文件。

响应：文件流。

### DELETE /files/{file_id}

用途：删除文件。

响应：

```json
{
  "deleted": true
}
```

## 5. 知识库问答

### POST /chat/conversations

用途：创建对话。

说明：

- 首期创建用户隔离的后端 conversation。
- 当前接口先保存会话和消息，为后续 Agent 多轮状态做准备。

响应：

```json
{
  "conversation_id": "conv-id"
}
```

### POST /chat/conversations/{conversation_id}/messages

用途：发送用户问题并获取回答。

说明：

- 首期用于知识库问答。
- 当前实现保留 sources 字段。
- 真实 RAG 通过后端 service 懒加载旧 `rag.py` / `vector_db.py` 逻辑。
- 测试中通过 mock RAG answerer 避免调用外部模型和向量库。
- 当前 Chat API 已作为 Agent 对话入口，响应会保留 `route` 和 `data`，用于承载工具调用后的结构化结果。

请求：

```json
{
  "message": "请解释某个 TSU 功能",
  "use_knowledge_base": true
}
```

响应：

```json
{
  "conversation_id": "conv-id",
  "answer": "回答内容",
  "sources": [
    {
      "file_name": "doc.pdf",
      "page_number": 3,
      "snippet": "引用片段"
    }
  ],
  "route": "rag",
  "data": {
    "sources": [
      {
        "file_name": "doc.pdf",
        "page_number": 3,
        "snippet": "引用片段"
      }
    ]
  }
}
```

当 Agent 调用任务类工具时，`route` 可能为 `translation`、`spi`、`diff`，`data` 会包含对应任务信息：

```json
{
  "conversation_id": "conv-id",
  "answer": "翻译任务已创建，状态：succeeded",
  "sources": [],
  "route": "translation",
  "data": {
    "task_id": "task-id",
    "status": "succeeded",
    "result_file_id": "result-file-id",
    "error": null
  }
}
```

后续可扩展：

- SSE 流式回答接口。
- 对话历史接口。
- 答案评价接口。

## 6. 文档翻译

### POST /translation/tasks

用途：创建文档翻译任务。

说明：

- `target_language` 必填，不提供默认目标语言。
- 首期支持 `.pptx`、`.xlsx`、`.docx`。
- 解析结果面向用户只提供最终翻译文件。
- 当前实现为同步执行并记录任务结果，接口保持任务化，后续可迁移到后台 worker。

请求：

```json
{
  "file_id": "file-id",
  "target_language": "英语"
}
```

响应：

```json
{
  "task_id": "task-id",
  "status": "pending"
}
```

### GET /translation/tasks/{task_id}

用途：查询翻译任务状态。

响应：

```json
{
  "task_id": "task-id",
  "status": "succeeded",
  "progress": 100,
  "result_file_id": "translated-file-id",
  "error": null
}
```

## 7. SPI log 解析

### POST /spi/tasks

用途：创建 SPI log 解析任务。

说明：

- 首期输入为一个已上传的 `.log` 文件。
- 解析结果面向用户只提供最终 Excel 文件。
- 当前实现为同步执行并记录任务结果，接口保持任务化，后续可迁移到后台 worker。

请求：

```json
{
  "file_id": "file-id"
}
```

响应：

```json
{
  "task_id": "task-id",
  "status": "pending"
}
```

### GET /spi/tasks/{task_id}

用途：查询 SPI log 解析任务状态和结果。

响应：

```json
{
  "task_id": "task-id",
  "status": "succeeded",
  "result_file_id": "result-file-id",
  "error": null
}
```

## 8. 版本差分比较

### POST /diff/tasks

用途：创建版本差分比较任务。

说明：

- 首期输入文件为两个已上传的 `.tar.gz` 文件。
- 后端会自动解压压缩包。
- 后端会比较解压后 `bin` 和 `lib` 目录下的二进制文件尺寸差异。
- 当前实现为同步执行并记录任务结果，接口保持任务化，后续可迁移到后台 worker。

请求：

```json
{
  "left_file_id": "old-file-id",
  "right_file_id": "new-file-id",
  "mode": "auto"
}
```

响应：

```json
{
  "task_id": "task-id",
  "status": "pending"
}
```

### GET /diff/tasks/{task_id}

用途：查询差分任务状态和结果。

响应：

```json
{
  "task_id": "task-id",
  "status": "succeeded",
  "summary": {
    "changed": true,
    "added": 10,
    "removed": 5,
    "modified": 3
  },
  "result_file_id": "diff-result-file-id",
  "error": null
}
```

## 9. 通用任务接口

### GET /tasks/{task_id}

用途：按统一格式查询任务。

响应：

```json
{
  "task_id": "task-id",
  "type": "translation",
  "status": "running",
  "progress": 42,
  "created_at": "2026-05-18T10:00:00Z",
  "updated_at": "2026-05-18T10:01:00Z",
  "error": null
}
```

### POST /tasks/{task_id}/cancel

用途：取消任务。

响应：

```json
{
  "task_id": "task-id",
  "status": "cancelled"
}
```

## 10. 待确认 API 事项

- 是否需要管理员创建用户接口。
- 是否需要用户修改密码接口。
- 是否需要知识库文档管理接口。
- 是否需要部门共享文件接口。
- 是否需要对话历史列表和删除接口。
- 是否需要任务历史列表接口。
- 是否需要前端实时进度，采用轮询还是 SSE。
