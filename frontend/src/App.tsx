import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { checkHealth } from './api/client'
import ChatPage from './pages/ChatPage'
import DiffPage from './pages/DiffPage'
import FilesPage from './pages/FilesPage'
import LoginPage from './pages/LoginPage'
import PlaceholderPage from './pages/PlaceholderPage'
import SpiPage from './pages/SpiPage'
import TasksPage from './pages/TasksPage'
import TranslationPage from './pages/TranslationPage'
import type { User } from './types/auth'

type HealthState = 'checking' | 'ok' | 'error'

const routes = [
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
]

function App() {
  const [health, setHealth] = useState<HealthState>('checking')
  const [user, setUser] = useState<User | null>(null)
  const [accessToken, setAccessToken] = useState(() => window.localStorage.getItem('seki_access_token'))
  const [currentPath, setCurrentPath] = useState(() => window.location.hash.replace('#/', '') || 'login')

  useEffect(() => {
    checkHealth()
      .then(() => setHealth('ok'))
      .catch(() => setHealth('error'))
  }, [])

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
    setAccessToken(accessToken)
    setUser(user)
  }

  function renderPage() {
    if (activeRoute.path === 'login') {
      return <LoginPage onLogin={handleLogin} user={user} />
    }

    if (activeRoute.path === 'files') {
      return <FilesPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'chat') {
      return <ChatPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'translation') {
      return <TranslationPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'spi') {
      return <SpiPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'diff') {
      return <DiffPage accessToken={accessToken} />
    }

    if (activeRoute.path === 'tasks') {
      return <TasksPage accessToken={accessToken} />
    }

    return (
      <PlaceholderPage
        description={activeRoute.description}
        status={activeRoute.status}
        title={activeRoute.title}
      />
    )
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
          {routes.map((item) => (
            <a
              aria-current={activeRoute.path === item.path ? 'page' : undefined}
              href={`#/${item.path}`}
              key={item.path}
            >
              {item.title}
            </a>
          ))}
        </nav>
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
