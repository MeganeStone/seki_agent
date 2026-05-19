import { useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE_URL, login } from '../api/client'
import type { User } from '../types/auth'

type LoginPageProps = {
  user: User | null
  onLogin: (user: User, accessToken: string) => void
}

function LoginPage({ user, onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoginError('')

    try {
      const result = await login(username, password)
      onLogin(result.user, result.access_token)
      setPassword('')
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : '登录失败')
    }
  }

  return (
    <section className="login-panel" aria-labelledby="login-title">
      <div>
        <h2 id="login-title">内部账号登录</h2>
        <p>
          API Base URL: <code>{API_BASE_URL}</code>
        </p>
      </div>

      {user ? (
        <div className="login-success">
          <span>已登录</span>
          <strong>{user.username}</strong>
        </div>
      ) : (
        <form className="login-form" onSubmit={handleLogin}>
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit">登录</button>
          {loginError && <p className="form-error">{loginError}</p>}
        </form>
      )}
    </section>
  )
}

export default LoginPage
