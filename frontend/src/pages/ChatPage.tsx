import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { createConversation, sendChatMessage, streamChatMessage } from '../api/chat'
import { cancelCodeOperation, confirmCodeOperation, listCodeOperations } from '../api/codeOperations'
import { getDiffTask } from '../api/diff'
import { downloadFile } from '../api/files'
import { getSpiTask } from '../api/spi'
import { getTranslationTask } from '../api/translation'
import type { ChatTurn } from '../types/chat'
import type { CodeOperation } from '../types/codeOperations'

type ChatPageProps = {
  accessToken: string | null
}

function stringValue(data: Record<string, unknown>, key: string): string | null {
  // 工具返回的 data 是开放结构，前端展示前统一做类型收窄，避免渲染时报错。
  const value = data[key]
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

function taskDataFromResponse(task: Record<string, unknown>): Record<string, unknown> {
  return {
    task_id: task.task_id,
    status: task.status,
    result_file_id: task.result_file_id,
    error: task.error,
    summary: task.summary,
    result_text: task.result_text,
    updated_at: task.updated_at,
  }
}

function objectValue(data: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  const value = data?.[key]
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function codeOperationFromUnknown(value: unknown): CodeOperation | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as Partial<CodeOperation>
  if (typeof candidate.operation_id !== 'string') return null
  if (typeof candidate.status !== 'string') return null
  if (typeof candidate.operation_type !== 'string') return null

  return {
    operation_id: candidate.operation_id,
    conversation_id: typeof candidate.conversation_id === 'string' ? candidate.conversation_id : '',
    agent_name: typeof candidate.agent_name === 'string' ? candidate.agent_name : 'code_agent',
    operation_type: candidate.operation_type,
    status: candidate.status,
    payload: candidate.payload && typeof candidate.payload === 'object' && !Array.isArray(candidate.payload)
      ? (candidate.payload as Record<string, unknown>)
      : {},
    result: candidate.result ?? null,
    created_at: typeof candidate.created_at === 'string' ? candidate.created_at : '',
    updated_at: typeof candidate.updated_at === 'string' ? candidate.updated_at : '',
    expires_at: typeof candidate.expires_at === 'string' ? candidate.expires_at : '',
  }
}

function pendingOperationFromData(data: Record<string, unknown> | null): CodeOperation | null {
  return codeOperationFromUnknown(objectValue(data, 'pending_operation'))
}

function operationLabel(operationType: string): string {
  if (operationType === 'delete_path') return '删除文件/目录'
  if (operationType === 'run_allowed_command') return '执行命令'
  return operationType
}

function operationTarget(operation: CodeOperation): string | null {
  const path = operation.payload.path
  if (typeof path === 'string' && path) return path

  const command = operation.payload.command
  const args = operation.payload.args
  if (typeof command === 'string' && Array.isArray(args)) return [command, ...args.map(String)].join(' ')
  if (typeof command === 'string') return command

  const target = operation.payload.target
  return typeof target === 'string' && target ? target : null
}

function ChatPage({ accessToken }: ChatPageProps) {
  // ChatPage 同时承担普通对话、工具任务展示、code agent 待确认操作三个职责。
  // 这些状态暂时保留在页面内，等交互稳定后再考虑拆成更小组件。
  const [conversationId, setConversationId] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [message, setMessage] = useState('')
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [webSearchApiKey, setWebSearchApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [activeToolTurnId, setActiveToolTurnId] = useState('')
  const [activeOperationId, setActiveOperationId] = useState('')
  const [error, setError] = useState('')

  const canSend = useMemo(() => Boolean(accessToken && message.trim() && !loading), [
    accessToken,
    message,
    loading,
  ])

  async function ensureConversation(): Promise<string> {
    // 会话采用懒创建：用户第一次发送消息时才向后端创建 conversation。
    if (conversationId) return conversationId
    if (!accessToken) throw new Error('请先登录')

    const created = await createConversation(accessToken)
    setConversationId(created.conversation_id)
    return created.conversation_id
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!accessToken || !message.trim()) return

    const userMessage = message.trim()
    setMessage('')
    setError('')
    setLoading(true)
    setTurns((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: userMessage },
    ])

    try {
      const activeConversationId = await ensureConversation()
      const assistantTurnId = crypto.randomUUID()
      setTurns((current) => [
        ...current,
        {
          id: assistantTurnId,
          role: 'assistant',
          content: '',
          route: 'streaming',
        },
      ])

      const payload = {
        message: userMessage,
        use_knowledge_base: useKnowledgeBase,
        api_key: apiKey.trim() || undefined,
        web_search_api_key: webSearchApiKey.trim() || undefined,
      }
      let receivedStreamContent = false
      try {
        // 优先走 SSE。若浏览器/代理不支持或后端流失败，再回退到普通 POST。
        await streamChatMessage(accessToken, activeConversationId, payload, {
          onDelta: (text) => {
            receivedStreamContent = true
            setTurns((current) =>
              current.map((turn) =>
                turn.id === assistantTurnId ? { ...turn, content: `${turn.content}${text}` } : turn,
              ),
            )
          },
          onFinal: (response) => {
            setTurns((current) =>
              current.map((turn) =>
                turn.id === assistantTurnId
                  ? {
                      ...turn,
                      content: response.answer,
                      sources: response.sources,
                      route: response.route,
                      data: response.data,
                      pendingOperation: pendingOperationFromData(response.data),
                    }
                  : turn,
              ),
            )
          },
        })
      } catch (streamError) {
        if (receivedStreamContent) {
          throw streamError
        }
        const response = await sendChatMessage(accessToken, activeConversationId, payload)
        setTurns((current) =>
          current.map((turn) =>
            turn.id === assistantTurnId
              ? {
                  ...turn,
                  content: response.answer,
                  sources: response.sources,
                  route: response.route,
                  data: response.data,
                  pendingOperation: pendingOperationFromData(response.data),
                }
              : turn,
          ),
        )
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : '消息发送失败')
    } finally {
      setLoading(false)
    }
  }

  function handleNewConversation() {
    setConversationId('')
    setTurns([])
    setMessage('')
    setError('')
  }

  async function handleRefreshToolTurn(turn: ChatTurn) {
    if (!accessToken || !turn.route || !turn.data) return

    const taskId = stringValue(turn.data, 'task_id')
    if (!taskId) return

    setActiveToolTurnId(turn.id)
    setError('')
    try {
      let nextData: Record<string, unknown> | null = null
      if (turn.route === 'translation') {
        nextData = taskDataFromResponse(await getTranslationTask(accessToken, taskId))
      } else if (turn.route === 'spi') {
        nextData = taskDataFromResponse(await getSpiTask(accessToken, taskId))
      } else if (turn.route === 'diff') {
        nextData = taskDataFromResponse(await getDiffTask(accessToken, taskId))
      }

      if (nextData) {
        setTurns((current) =>
          current.map((item) =>
            item.id === turn.id
              ? {
                  ...item,
                  data: {
                    ...item.data,
                    ...nextData,
                  },
                }
              : item,
          ),
        )
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : '任务状态查询失败')
    } finally {
      setActiveToolTurnId('')
    }
  }

  async function handleDownloadToolResult(turn: ChatTurn) {
    if (!accessToken || !turn.data) return

    const resultFileId = stringValue(turn.data, 'result_file_id')
    if (!resultFileId) return

    setActiveToolTurnId(turn.id)
    setError('')
    try {
      await downloadFile(accessToken, {
        id: resultFileId,
        filename: `${turn.route ?? 'agent'}_${resultFileId}`,
        size: 0,
        created_at: new Date().toISOString(),
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : '结果文件下载失败')
    } finally {
      setActiveToolTurnId('')
    }
  }

  async function handleRefreshPendingOperations() {
    // code agent 需要确认的操作可能来自历史回答，刷新时会把后端 pending 列表合并回对话流。
    if (!accessToken || !conversationId) return

    setError('')
    try {
      const response = await listCodeOperations(accessToken, {
        conversationId,
        status: 'pending',
        limit: 20,
      })
      setTurns((current) => {
        const nextTurns = current.map((turn) => ({ ...turn }))
        const knownIds = new Set(
          nextTurns
            .map((turn) => turn.pendingOperation?.operation_id)
            .filter((value): value is string => Boolean(value)),
        )

        response.items.forEach((operation) => {
          if (knownIds.has(operation.operation_id)) {
            for (const turn of nextTurns) {
              if (turn.pendingOperation?.operation_id === operation.operation_id) {
                turn.pendingOperation = operation
                turn.data = { ...(turn.data ?? {}), pending_operation: operation }
              }
            }
            return
          }
          nextTurns.push({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: '有一个 code agent 操作正在等待确认。',
            route: 'code_agent',
            data: { pending_operation: operation },
            pendingOperation: operation,
          })
        })

        return nextTurns
      })
    } catch (error) {
      setError(error instanceof Error ? error.message : '待确认操作刷新失败')
    }
  }

  async function handlePendingOperationAction(turn: ChatTurn, action: 'confirm' | 'cancel') {
    if (!accessToken || !turn.pendingOperation) return

    setActiveOperationId(turn.pendingOperation.operation_id)
    setError('')
    try {
      const operation = action === 'confirm'
        ? await confirmCodeOperation(accessToken, turn.pendingOperation.operation_id)
        : await cancelCodeOperation(accessToken, turn.pendingOperation.operation_id)
      setTurns((current) =>
        current.map((item) =>
          item.id === turn.id
            ? {
                ...item,
                pendingOperation: operation,
                data: {
                  ...(item.data ?? {}),
                  pending_operation: operation,
                },
              }
            : item,
        ),
      )
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : action === 'confirm'
            ? '待确认操作执行失败'
            : '待确认操作取消失败',
      )
    } finally {
      setActiveOperationId('')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>知识库问答 / Agent 入口</h2>
          <p>请先登录后再开始对话。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  return (
    <section className="chat-page" aria-labelledby="chat-title">
      <div className="chat-toolbar">
        <div>
          <h2 id="chat-title">知识库问答 / Agent 入口</h2>
          <p>{conversationId ? `conversation: ${conversationId}` : '新对话将在首次发送时创建'}</p>
        </div>
        <div className="chat-toolbar-actions">
          {conversationId && (
            <button type="button" onClick={() => void handleRefreshPendingOperations()}>
              刷新待确认
            </button>
          )}
          <button type="button" onClick={handleNewConversation}>
            新对话
          </button>
        </div>
      </div>

      <div className="chat-feed" aria-live="polite">
        {turns.length === 0 && (
          <div className="empty-state">可以直接聊天，也可以让 Agent 查询知识库或调用已接入的业务工具。</div>
        )}

        {turns.map((turn) => {
          const taskId = turn.data ? stringValue(turn.data, 'task_id') : null
          const status = turn.data ? stringValue(turn.data, 'status') : null
          const resultFileId = turn.data ? stringValue(turn.data, 'result_file_id') : null
          const toolError = turn.data ? stringValue(turn.data, 'error') : null
          const canRefreshTool = Boolean(taskId && ['translation', 'spi', 'diff'].includes(turn.route ?? ''))
          const toolActionLoading = activeToolTurnId === turn.id
          const pendingOperation = turn.pendingOperation ?? pendingOperationFromData(turn.data ?? null)
          const operationBusy = pendingOperation?.operation_id === activeOperationId
          const operationResultMessage = pendingOperation?.result?.message ?? null
          const operationTargetText = pendingOperation ? operationTarget(pendingOperation) : null

          return (
            <article className={`chat-turn ${turn.role}`} key={turn.id}>
              <strong>{turn.role === 'user' ? '你' : 'Seki Agent'}</strong>
              <p>{turn.content}</p>
              {turn.sources && turn.sources.length > 0 && (
                <div className="source-list">
                  {turn.sources.map((source, index) => (
                    <span key={`${source.file_name}-${index}`}>
                      {source.file_name ?? '未知来源'}
                      {source.page_number ? ` / ${source.page_number}` : ''}
                    </span>
                  ))}
                </div>
              )}
              {turn.data && (
                <div className="tool-result">
                  <span>{turn.route ? `工具：${turn.route}` : '工具结果'}</span>
                  {taskId && <span>任务：{taskId}</span>}
                  {status && <span>状态：{status}</span>}
                  {resultFileId && <span>结果文件：{resultFileId}</span>}
                  {toolError && <span className="tool-error">错误：{toolError}</span>}
                  {canRefreshTool && (
                    <button
                      type="button"
                      onClick={() => void handleRefreshToolTurn(turn)}
                      disabled={toolActionLoading}
                    >
                      {toolActionLoading ? '处理中' : '查询状态'}
                    </button>
                  )}
                  {resultFileId && (
                    <button
                      type="button"
                      onClick={() => void handleDownloadToolResult(turn)}
                      disabled={toolActionLoading}
                    >
                      下载结果
                    </button>
                  )}
                </div>
              )}
              {pendingOperation && (
                <div className="pending-operation">
                  <div>
                    <strong>{operationLabel(pendingOperation.operation_type)}</strong>
                    <span className={`status-badge ${pendingOperation.status}`}>{pendingOperation.status}</span>
                  </div>
                  {operationTargetText && <p>目标：{operationTargetText}</p>}
                  <p>确认后会由后端继续执行，并把结果写回当前对话。</p>
                  {operationResultMessage && <p>结果：{operationResultMessage}</p>}
                  {pendingOperation.status === 'pending' && (
                    <div className="pending-actions">
                      <button
                        type="button"
                        onClick={() => void handlePendingOperationAction(turn, 'confirm')}
                        disabled={operationBusy}
                      >
                        {operationBusy ? '处理中' : '确认执行'}
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void handlePendingOperationAction(turn, 'cancel')}
                        disabled={operationBusy}
                      >
                        取消
                      </button>
                    </div>
                  )}
                </div>
              )}
            </article>
          )
        })}

        {loading && <div className="empty-state">正在生成回答...</div>}
      </div>

      {error && <p className="form-error">{error}</p>}

      <form className="chat-input" onSubmit={handleSubmit}>
        <label className="toggle-line">
          <input
            checked={useKnowledgeBase}
            onChange={(event) => setUseKnowledgeBase(event.target.checked)}
            type="checkbox"
          />
          使用知识库 / RAG
        </label>
        <input
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="千问 API key（可选，后端环境配置优先生效）"
          type="password"
          autoComplete="off"
        />
        <input
          value={webSearchApiKey}
          onChange={(event) => setWebSearchApiKey(event.target.value)}
          placeholder="火山搜索 API key（可选，后端环境配置优先生效）"
          type="password"
          autoComplete="off"
        />
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="输入问题、业务查询或代码任务..."
          rows={3}
        />
        <button type="submit" disabled={!canSend}>
          {loading ? '发送中' : '发送'}
        </button>
      </form>
    </section>
  )
}

export default ChatPage
