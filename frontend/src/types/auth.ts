export type User = {
  id: string
  username: string
  is_admin?: boolean
}

export type LoginResponse = {
  access_token: string
  token_type: string
  user: User
}

export type AdminUser = {
  username: string
  is_admin: boolean
  created_at: string
  updated_at: string
}
