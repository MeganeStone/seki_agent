import { useCallback, useEffect, useState } from 'react'
import { createAdminUser, deleteAdminUser, listAdminUsers } from '../api/adminUsers'
import type { AdminUser } from '../types/auth'

type AdminUsersPageProps = {
  accessToken: string | null
  currentUsername: string | null
  isAdmin: boolean
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function AdminUsersPage({ accessToken, currentUsername, isAdmin }: AdminUsersPageProps) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newIsAdmin, setNewIsAdmin] = useState(false)

  const refreshUsers = useCallback(async () => {
    if (!accessToken) return
    setLoading(true)
    setError('')
    try {
      setUsers(await listAdminUsers(accessToken))
    } catch (error) {
      setError(error instanceof Error ? error.message : '加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }, [accessToken])

  useEffect(() => {
    if (!accessToken || !isAdmin) return

    let isCurrent = true
    const token = accessToken

    async function loadUsers() {
      setLoading(true)
      setError('')
      try {
        const result = await listAdminUsers(token)
        if (isCurrent) setUsers(result)
      } catch (error) {
        if (isCurrent) setError(error instanceof Error ? error.message : '加载用户列表失败')
      } finally {
        if (isCurrent) setLoading(false)
      }
    }

    void loadUsers()

    return () => {
      isCurrent = false
    }
  }, [accessToken, isAdmin])

  async function handleCreate() {
    if (!accessToken || !newUsername.trim() || !newPassword) return
    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const created = await createAdminUser(accessToken, newUsername.trim(), newPassword, newIsAdmin)
      setMessage(`已创建/更新用户：${created.username}`)
      setNewUsername('')
      setNewPassword('')
      setNewIsAdmin(false)
      await refreshUsers()
    } catch (error) {
      setError(error instanceof Error ? error.message : '创建用户失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(username: string) {
    if (!accessToken) return
    const confirmed = window.confirm(
      `确认删除用户 ${username}？该用户的文件、任务、对话和审计数据会一并删除，且无法恢复。`,
    )
    if (!confirmed) return

    setError('')
    setMessage('')
    try {
      await deleteAdminUser(accessToken, username)
      setMessage(`已删除用户：${username}`)
      await refreshUsers()
    } catch (error) {
      setError(error instanceof Error ? error.message : '删除用户失败')
    }
  }

  if (!accessToken) {
    return (
      <section className="feature-panel">
        <div>
          <h2>用户管理</h2>
          <p>请先登录。</p>
        </div>
        <a className="text-action" href="#/login">
          去登录
        </a>
      </section>
    )
  }

  if (!isAdmin) {
    return (
      <section className="feature-panel">
        <div>
          <h2>用户管理</h2>
          <p>当前账号没有管理员权限。</p>
        </div>
      </section>
    )
  }

  return (
    <section className="files-page" aria-labelledby="admin-users-title">
      <div className="files-toolbar">
        <div>
          <h2 id="admin-users-title">用户管理</h2>
          <p>{loading ? '正在刷新用户列表' : `共 ${users.length} 个用户`}</p>
        </div>
        <button type="button" onClick={refreshUsers} disabled={loading}>
          刷新
        </button>
      </div>

      <div className="upload-panel">
        <input
          placeholder="用户名"
          value={newUsername}
          onChange={(event) => setNewUsername(event.target.value)}
          disabled={submitting}
        />
        <input
          placeholder="密码"
          type="password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          disabled={submitting}
        />
        <label className="toggle-line">
          <input
            type="checkbox"
            checked={newIsAdmin}
            onChange={(event) => setNewIsAdmin(event.target.checked)}
            disabled={submitting}
          />
          管理员
        </label>
        <button type="button" onClick={handleCreate} disabled={submitting || !newUsername.trim() || !newPassword}>
          {submitting ? '提交中' : '创建用户'}
        </button>
      </div>

      {message && <p className="form-message">{message}</p>}
      {error && <p className="form-error">{error}</p>}

      <div className="file-table" role="table" aria-label="用户列表">
        <div className="file-row file-head" role="row">
          <span role="columnheader">用户名</span>
          <span role="columnheader">角色</span>
          <span role="columnheader">创建时间</span>
          <span role="columnheader">操作</span>
        </div>

        {users.map((user) => (
          <div className="file-row" role="row" key={user.username}>
            <span role="cell">{user.username}</span>
            <span role="cell">{user.is_admin ? '管理员' : '普通用户'}</span>
            <span role="cell">{formatDate(user.created_at)}</span>
            <span className="file-actions" role="cell">
              <button
                type="button"
                onClick={() => handleDelete(user.username)}
                disabled={user.username === currentUsername}
                title={user.username === currentUsername ? '不能删除当前登录账号' : undefined}
              >
                删除
              </button>
            </span>
          </div>
        ))}

        {!loading && users.length === 0 && <div className="empty-state">暂无用户</div>}
      </div>
    </section>
  )
}

export default AdminUsersPage
