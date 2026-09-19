import { useCallback, useEffect, useState } from 'react'
import { authStatus, logout as apiLogout } from '../utils/api'

/**
 * Session state for the dashboard.
 *
 * Asks the API what the rules are rather than assuming them. A deployment with
 * no account configured must not put a login screen in front of itself, and a
 * build cannot know which kind it is talking to -- so `/api/auth/status` is the
 * first call, and `gated` comes from the answer.
 *
 * `checking` starts true so nothing renders during the round trip. Defaulting
 * it false flashes the whole dashboard for a moment before the login screen
 * replaces it, which looks like a leak even though the API would refuse every
 * request that flash tried to make.
 */
export function useAuth() {
  const [checking, setChecking] = useState(true)
  const [required, setRequired] = useState(false)
  const [user, setUser] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const status = await authStatus()
      setRequired(Boolean(status.auth_required))
      setUser(
        status.authenticated ? { username: status.username, display_name: status.username } : null,
      )
    } catch {
      // The status probe is public and cheap. If it fails the backend is
      // unreachable, which the dashboard already reports on its own -- so fail
      // open here rather than showing a login screen for a server that cannot
      // authenticate anyone anyway.
      setRequired(false)
      setUser(null)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const signOut = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      // Clear locally whatever the server said. A logout that appears to fail
      // must not leave the browser looking signed in.
      setUser(null)
    }
  }, [])

  return {
    checking,
    user,
    signOut,
    signIn: setUser,
    // Show the login screen only when the server demands it and nobody is in.
    gated: required && !user,
  }
}
