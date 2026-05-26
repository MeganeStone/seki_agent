const USERNAME_STORAGE_KEY = 'seki_username'

export function persistUsername(username: string): void {
  window.localStorage.setItem(USERNAME_STORAGE_KEY, username)
}

export function readStoredUsername(): string | null {
  return window.localStorage.getItem(USERNAME_STORAGE_KEY)
}

export function clearStoredUsername(): void {
  window.localStorage.removeItem(USERNAME_STORAGE_KEY)
}

export function scopedStorageKey(baseKey: string, username: string | null | undefined): string {
  const safeUsername = username?.trim()
  if (!safeUsername) return baseKey
  return `${baseKey}:${safeUsername}`
}
