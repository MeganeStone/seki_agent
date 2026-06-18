import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { checkHealth, fetchMe } from './api/client'
import AdminUsersPage from './pages/AdminUsersPage'
import ChatPage from './pages/ChatPage'
import DiffPage from './pages/DiffPage'
import FilesPage from './pages/FilesPage'
import LoginPage from './pages/LoginPage'
import SpiPage from './pages/SpiPage'
import TasksPage from './pages/TasksPage'
import TracePage from './pages/TracePage'
import TranslationPage from './pages/TranslationPage'
import type { User } from './types/auth'
import { clearStoredUsername, persistUsername, readStoredUsername } from './utils/storageScope'

type HealthState = 'checking' | 'ok' | 'error'

type RouteDef = {
  path: string
  title: string
  description: string
  status: string
  adminOnly?: boolean
}

const routes: RouteDef[] = [
  // 当前前端使用 hash route，避免本地 Vite 和静态部署时额外配置 history fallback。
  {
    path: 'login',
    title: '登录',
    description: '内部账号登录和后端健康检查。',
    status: '可验证',
  },
  {
    path: 'chat',
    title: 'Agent 入口',
    description: '通过对话调用知识库、翻译、SPI 解析和版本差分工具。',
    status: '可验证',
  },
  {
    path: 'files',
    title: '文件管理',
    description: '按用户隔离上传、下载和删除文件。',
    status: '可验证',
  },
  {
    path: 'translation',
    title: '文档翻译',
    description: '上传 Office 文档并选择目标语言。',
    status: '可验证',
  },
  {
    path: 'spi',
    title: 'SPI log 解析',
    description: '解析 log 并下载 Excel 结果。',
    status: '可验证',
  },
  {
    path: 'diff',
    title: '版本差分比较',
    description: '比较两个 tar.gz 版本包的 bin/lib 差异。',
    status: '可验证',
  },
  {
    path: 'tasks',
    title: '任务历史',
    description: '查看翻译、SPI 解析和版本差分的最近任务。',
    status: '可验证',
  },
  {
    path: 'trace',
    title: '运行追踪',
    description: '查看 Agent 每轮运行的工具调用、token 用量和耗时。',
    status: '可验证',
  },
  {
    path: 'admin-users',
    title: '用户管理',
    description: '管理员创建、查询和删除用户。',
    status: '可验证',
    adminOnly: true,
  },
]

function App() {
  // accessToken 放在 localStorage，刷新页面后仍能继续访问需要登录的功能。
  const [health, setHealth] = useState<HealthState>('checking')
  const [user, setUser] = useState<User | null>(() => {
    const username = readStoredUsername()
    return username ? { id: username, username } : null
  })
  const [accessToken, setAccessToken] = useState(() => window.localStorage.getItem('seki_access_token'))
  const [currentPath, setCurrentPath] = useState(() => window.location.hash.replace('#/', '') || 'login')

  useEffect(() => {
    checkHealth()
      .then(() => setHealth('ok'))
      .catch(() => setHealth('error'))
  }, [])

  // 刷新页面后 localStorage 只有用户名，向后端拉一次当前用户补齐 is_admin。
  useEffect(() => {
    if (!accessToken) return
    fetchMe(accessToken)
      .then((me) => setUser(me))
      .catch(() => {
        // token 失效时回到未登录状态。
        window.localStorage.removeItem('seki_access_token')
        clearStoredUsername()
        setAccessToken(null)
        setUser(null)
      })
  }, [accessToken])

  useEffect(() => {
    function handleHashChange() {
      setCurrentPath(window.location.hash.replace('#/', '') || 'login')
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const healthLabel = useMemo(() => {
    if (health === 'checking') return '检查中'
    if (health === 'ok') return '后端在线'
    return '后端不可用'
  }, [health])

  const activeRoute = routes.find((route) => route.path === currentPath) ?? routes[0]

  function handleLogin(user: User, accessToken: string) {
    window.localStorage.setItem('seki_access_token', accessToken)
    persistUsername(user.username)
    setAccessToken(accessToken)
    setUser(user)
    window.location.hash = '#/chat'
  }

  function handleLogout() {
    window.localStorage.removeItem('seki_access_token')
    clearStoredUsername()
    setAccessToken(null)
    setUser(null)
    window.location.hash = '#/login'
  }

  function renderPage() {
    // 这里保持显式分发，页面数量不多时比引入路由库更直观，也方便迁移初期调试。
    if (activeRoute.path === 'login') {
      return <LoginPage onLogin={handleLogin} user={user} />
    }

    if (activeRoute.path === 'files') {
      return <FilesPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'chat') {
      return <ChatPage accessToken={accessToken} username={user?.username ?? null} />
    }

    if (activeRoute.path === 'translation') {
      return <TranslationPage accessToken={accessToken} username={user?.username ?? null} />
    }

    if (activeRoute.path === 'spi') {
      return <SpiPage accessToken={accessToken} username={user?.username ?? null} />
    }

    if (activeRoute.path === 'diff') {
      return <DiffPage accessToken={accessToken} username={user?.username ?? null} />
    }

    if (activeRoute.path === 'tasks') {
      return <TasksPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'trace') {
      return <TracePage accessToken={accessToken} />
    }

    if (activeRoute.path === 'admin-users') {
      return (
        <AdminUsersPage
          accessToken={accessToken}
          currentUsername={user?.username ?? null}
          isAdmin={Boolean(user?.is_admin)}
        />
      )
    }

    return <LoginPage onLogin={handleLogin} user={user} />
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">S</span>
          <div>
            <strong>Seki Agent</strong>
            <span>工程化工作台</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="主导航">
          {routes
            .filter((item) => !item.adminOnly || user?.is_admin)
            .map((item) => (
            <a
              aria-current={activeRoute.path === item.path ? 'page' : undefined}
              href={`#/${item.path}`}
              key={item.path}
            >
              {item.title}
            </a>
          ))}
        </nav>

        <div className="account-panel">
          <span>{user ? user.username : '未登录'}</span>
          {user ? (
            <button type="button" onClick={handleLogout}>
              退出登录
            </button>
          ) : (
            <a href="#/login">登录</a>
          )}
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{activeRoute.title}</h1>
            <p>{activeRoute.description}</p>
          </div>
          <div className={`health-pill ${health}`}>
            <span />
            {healthLabel}
          </div>
        </header>

        {renderPage()}
      </section>
    </main>
  )
}

export default App
