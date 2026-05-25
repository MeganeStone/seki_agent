export type ConversationCreateResponse = {
  conversation_id: string
  created_at: string
}

export type ChatSource = {
  file_name: string | null
  page_number: string | number | null
  snippet: string | null
}

export type ChatMessageResponse = {
  conversation_id: string
  answer: string
  sources: ChatSource[]
  route: string | null
  data: Record<string, unknown> | null
}

export type ChatMessageRead = {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'tool' | string
  content: string
  created_at: string
}

export type SendChatMessagePayload = {
  message: string
  use_knowledge_base: boolean
}

export type ChatTurn = {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  sources?: ChatSource[]
  route?: string | null
  data?: Record<string, unknown> | null
  pendingOperation?: CodeOperation | null
}
import type { CodeOperation } from './codeOperations'
