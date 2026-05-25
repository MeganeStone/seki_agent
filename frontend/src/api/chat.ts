import { API_BASE_URL } from './client'
import type {
  ChatMessageRead,
  ChatMessageResponse,
  ConversationCreateResponse,
  SendChatMessagePayload,
} from '../types/chat'

function authHeaders(accessToken: string): HeadersInit {
  // Chat 接口都需要 Bearer token，且请求体统一使用 JSON。
  return {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  }
}

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json()
    if (typeof payload?.detail === 'string') return new Error(payload.detail)
    if (typeof payload?.message === 'string') return new Error(payload.message)
  } catch {
    // 非 JSON 错误响应时保留中文兜底文案。
  }

  return new Error(fallback)
}

export async function createConversation(accessToken: string): Promise<ConversationCreateResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/conversations`, {
    method: 'POST',
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '对话创建失败')
  }

  return response.json()
}

export async function sendChatMessage(
  accessToken: string,
  conversationId: string,
  payload: SendChatMessagePayload,
): Promise<ChatMessageResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw await parseError(response, '消息发送失败')
  }

  return response.json()
}

export async function listChatMessages(
  accessToken: string,
  conversationId: string,
): Promise<ChatMessageRead[]> {
  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '对话历史获取失败')
  }

  return response.json()
}

type StreamHandlers = {
  onDelta: (text: string) => void
  onFinal: (response: ChatMessageResponse) => void
}

export async function streamChatMessage(
  accessToken: string,
  conversationId: string,
  payload: SendChatMessagePayload,
  handlers: StreamHandlers,
): Promise<void> {
  // 浏览器 fetch 没有直接暴露 EventSource 风格的 POST SSE，所以这里手动读取
  // ReadableStream 并解析 `event:` / `data:` 块。
  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw await parseError(response, '消息发送失败')
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''

    for (const eventText of events) {
      const event = parseSseEvent(eventText)
      if (!event) continue
      if (event.event === 'delta') {
        const payload = JSON.parse(event.data) as { text?: string }
        if (payload.text) handlers.onDelta(payload.text)
      } else if (event.event === 'final') {
        handlers.onFinal(JSON.parse(event.data) as ChatMessageResponse)
      }
    }
  }
}

function parseSseEvent(text: string): { event: string; data: string } | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of text.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}
