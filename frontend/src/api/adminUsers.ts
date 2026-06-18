import { API_BASE_URL } from './client'
import type { AdminUser } from '../types/auth'

export async function listAdminUsers(accessToken: string): Promise<AdminUser[]> {
  const response = await fetch(`${API_BASE_URL}/admin/users`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    throw new Error(`加载用户列表失败：${response.status}`)
  }
  const body = await response.json()
  return body.items as AdminUser[]
}

export async function createAdminUser(
  accessToken: string,
  username: string,
  password: string,
  isAdmin: boolean,
): Promise<AdminUser> {
  const response = await fetch(`${API_BASE_URL}/admin/users`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ username, password, is_admin: isAdmin }),
  })
  if (!response.ok) {
    throw new Error(`创建用户失败：${response.status}`)
  }
  return response.json()
}

export async function deleteAdminUser(accessToken: string, username: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/admin/users/${encodeURIComponent(username)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    const detail = await response.json().then((body) => body.detail).catch(() => null)
    throw new Error(detail ?? `删除用户失败：${response.status}`)
  }
}
