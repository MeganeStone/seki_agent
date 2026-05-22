import { API_BASE_URL } from './client'
import type { CodeOperation, CodeOperationListResponse } from '../types/codeOperations'

function authHeaders(accessToken: string): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
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

export async function listCodeOperations(
  accessToken: string,
  options: { conversationId?: string; status?: string; limit?: number } = {},
): Promise<CodeOperationListResponse> {
  const params = new URLSearchParams()
  if (options.conversationId) params.set('conversation_id', options.conversationId)
  if (options.status) params.set('status', options.status)
  params.set('limit', String(options.limit ?? 50))

  const response = await fetch(`${API_BASE_URL}/code-operations?${params.toString()}`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '待确认操作获取失败')
  }

  return response.json()
}

export async function confirmCodeOperation(accessToken: string, operationId: string): Promise<CodeOperation> {
  const response = await fetch(`${API_BASE_URL}/code-operations/${operationId}/confirm`, {
    method: 'POST',
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '待确认操作执行失败')
  }

  return response.json()
}

export async function cancelCodeOperation(accessToken: string, operationId: string): Promise<CodeOperation> {
  const response = await fetch(`${API_BASE_URL}/code-operations/${operationId}/cancel`, {
    method: 'POST',
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '待确认操作取消失败')
  }

  return response.json()
}
