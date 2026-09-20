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
 * The probe NEVER blocks rendering. An earlier version held a blank screen
 * until it answered, on the reasoning that flashing the dashboard before a
 * login screen looks like a leak. It is not one -- the API refuses every
 * request such a flash could make -- and the cost was severe: against a
 * sleeping backend the site was a black rectangle for minutes, which is how it
 * reached production and how it was reported.
 *
 * So the dashboard renders immediately and the login screen replaces it only
 * once the server has positively said authentication is required.
 */
export function useAuth() {
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
      // authStatus() already resolves rather than throwing, so this is
      // belt-and-braces: a probe that cannot answer must never gate the app.
      setRequired(false)
      setUser(null)
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
    user,
    signOut,
    signIn: setUser,
    // Show the login screen only when the server demands it and nobody is in.
    gated: required && !user,
  }
}
