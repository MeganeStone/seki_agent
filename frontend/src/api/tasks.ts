import { API_BASE_URL } from './client'
import type { TaskListResponse, UnifiedTask } from '../types/tasks'

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

export async function listTasks(accessToken: string, limit = 50): Promise<TaskListResponse> {
  const response = await fetch(`${API_BASE_URL}/tasks?limit=${encodeURIComponent(String(limit))}`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '任务历史获取失败')
  }

  return response.json()
}

export async function getTask(accessToken: string, taskId: string): Promise<UnifiedTask> {
  const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '任务查询失败')
  }

  return response.json()
}

export async function cancelTask(accessToken: string, taskId: string): Promise<UnifiedTask> {
  const response = await fetch(`${API_BASE_URL}/tasks/${taskId}/cancel`, {
    method: 'POST',
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, '任务取消失败')
  }

  return response.json()
}
