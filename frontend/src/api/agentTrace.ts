import { API_BASE_URL } from './client'

export type AgentTraceEvent = {
  event_id: string
  seq: number
  event_type: string
  name: string
  status: string
  preview: string
  error: string | null
  input_tokens: number | null
  output_tokens: number | null
  duration_ms: number | null
  created_at: string
}

export type AgentTraceRun = {
  run_id: string
  conversation_id: string
  agent_name: string
  status: string
  input_preview: string
  answer_preview: string
  error: string | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  started_at: string
  finished_at: string | null
  duration_ms: number | null
}

export async function listTraceRuns(
  accessToken: string,
  conversationId?: string,
  limit = 50,
): Promise<AgentTraceRun[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (conversationId) params.set('conversation_id', conversationId)
  const response = await fetch(`${API_BASE_URL}/agent-trace/runs?${params}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    throw new Error(`运行追踪列表获取失败：${response.status}`)
  }
  const body = await response.json()
  return body.items as AgentTraceRun[]
}

export async function getTraceRunDetail(
  accessToken: string,
  runId: string,
): Promise<{ run: AgentTraceRun; events: AgentTraceEvent[] }> {
  const response = await fetch(`${API_BASE_URL}/agent-trace/runs/${runId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    throw new Error(`运行追踪详情获取失败：${response.status}`)
  }
  return response.json()
}
