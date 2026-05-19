import { API_BASE_URL } from './client'
import type { ChatMessageResponse, ConversationCreateResponse } from '../types/chat'

function authHeaders(accessToken: string): HeadersInit {
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
    // Keep fallback for non-JSON error responses.
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
  message: string,
  useKnowledgeBase: boolean,
): Promise<ChatMessageResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: authHeaders(accessToken),
    body: JSON.stringify({
      message,
      use_knowledge_base: useKnowledgeBase,
    }),
  })

  if (!response.ok) {
    throw await parseError(response, '消息发送失败')
  }

  return response.json()
}
