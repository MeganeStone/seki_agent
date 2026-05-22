export type TranslationTask = {
  task_id: string
  status: string
  target_language: string
  result_file_id: string | null
  result_filename: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type CreateTranslationTaskPayload = {
  file_id: string
  target_language: string
  api_key?: string
}
