export type CodeOperationResult = {
  status: string | null
  message: string | null
  data: Record<string, unknown>
}

export type CodeOperation = {
  operation_id: string
  conversation_id: string
  agent_name: string
  operation_type: string
  status: string
  payload: Record<string, unknown>
  result: CodeOperationResult | null
  created_at: string
  updated_at: string
  expires_at: string
}

export type CodeOperationListResponse = {
  items: CodeOperation[]
}
