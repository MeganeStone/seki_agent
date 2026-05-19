import { API_BASE_URL } from './client'
import type { CreateSpiTaskPayload, SpiTask } from '../types/spi'

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

export async function createSpiTask(
  accessToken: string,
  payload: CreateSpiTaskPayload,
): Promise<SpiTask> {
  const response = await fetch(`${API_BASE_URL}/spi/tasks`, {
    method: 'POST',
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw await parseError(response, 'SPI 解析任务创建失败')
  }

  return response.json()
}

export async function getSpiTask(accessToken: string, taskId: string): Promise<SpiTask> {
  const response = await fetch(`${API_BASE_URL}/spi/tasks/${taskId}`, {
    headers: authHeaders(accessToken),
  })

  if (!response.ok) {
    throw await parseError(response, 'SPI 解析任务查询失败')
  }

  return response.json()
}
