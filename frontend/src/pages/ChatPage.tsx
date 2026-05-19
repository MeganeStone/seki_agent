import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { createConversation, sendChatMessage } from '../api/chat'
import { getDiffTask } from '../api/diff'
import { downloadFile } from '../api/files'
import { getSpiTask } from '../api/spi'
import { getTranslationTask } from '../api/translation'
import type { ChatTurn } from '../types/chat'

type ChatPageProps = {
  accessToken: string | null
}

function stringValue(data: Record<string, unknown>, key: string): string | null {
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

function ChatPage({ accessToken }: ChatPageProps) {
  const [conversationId, setConversationId] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [message, setMessage] = useState('')
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true)
  const [loading, setLoading] = useState(false)
  const [activeToolTurnId, setActiveToolTurnId] = useState('')
  const [error, setError] = useState('')

  const canSend = useMemo(() => Boolean(accessToken && message.trim() && !loading), [
    accessToken,
    message,
    loading,
  ])

  async function ensureConversation(): Promise<string> {
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
      const response = await sendChatMessage(
        accessToken,
        activeConversationId,
        userMessage,
        useKnowledgeBase,
      )
      setTurns((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          route: response.route,
          data: response.data,
        },
      ])
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
        <button type="button" onClick={handleNewConversation}>
          新对话
        </button>
      </div>

      <div className="chat-feed" aria-live="polite">
        {turns.length === 0 && (
          <div className="empty-state">可以先问一个公司业务问题，后续这里会接入完整 Agent 编排。</div>
        )}

        {turns.map((turn) => {
          const taskId = turn.data ? stringValue(turn.data, 'task_id') : null
          const status = turn.data ? stringValue(turn.data, 'status') : null
          const resultFileId = turn.data ? stringValue(turn.data, 'result_file_id') : null
          const toolError = turn.data ? stringValue(turn.data, 'error') : null
          const canRefreshTool = Boolean(taskId && ['translation', 'spi', 'diff'].includes(turn.route ?? ''))
          const toolActionLoading = activeToolTurnId === turn.id

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
          使用知识库
        </label>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="输入问题或任务..."
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
