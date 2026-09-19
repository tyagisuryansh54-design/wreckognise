import { useEffect, useRef, useState } from 'react'
import { login } from '../utils/api'

/**
 * Sign-in screen.
 *
 * Deliberately says nothing the server did not. The API answers every failure
 * with the same "Invalid credentials", and this screen repeats it verbatim
 * rather than helpfully distinguishing "no such user" from "wrong password" --
 * that distinction is how an attacker maps who holds an account.
 */
export default function LoginPage({ onAuthenticated }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const firstField = useRef(null)

  useEffect(() => {
    firstField.current?.focus()
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const session = await login(username, password)
      onAuthenticated(session.user)
    } catch (err) {
      // 429 is worth distinguishing: it is not a credential problem, and
      // leaving it as "Invalid credentials" sends people round a loop trying
      // passwords that were never going to be read.
      setError(
        err?.status === 429
          ? 'Too many attempts. Wait a minute and try again.'
          : 'Invalid credentials.',
      )
      setPassword('')
      setBusy(false)
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center px-5 py-16">
      {/* Grid wash, matching the dashboard's ground. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'linear-gradient(to right, rgba(0,255,45,0.05) 1px, transparent 1px),' +
            'linear-gradient(to bottom, rgba(0,255,45,0.05) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
        }}
      />

      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-[2px] bg-azure" />
          <span className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-ink">
            Wreckognise
          </span>
        </div>

        <p className="font-mono text-2xs text-azure">/* restricted */</p>
        <h1 className="mt-1.5 font-display text-2xl font-bold text-ink">Sign in.</h1>
        <p className="mt-2 font-mono text-2xs text-ink/40">
          Survey console · authorised operators only
        </p>

        <form onSubmit={submit} className="mt-7 space-y-4" noValidate>
          <div>
            <label
              htmlFor="username"
              className="font-mono text-2xs uppercase tracking-wide text-ink/40"
            >
              Operator
            </label>
            <input
              ref={firstField}
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              required
              className="mt-1.5 w-full rounded-bento border border-ink/15 bg-sand px-3.5 py-2.5 font-mono text-sm text-ink outline-none transition-colors placeholder:text-ink/25 focus:border-azure/70 disabled:opacity-50"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="font-mono text-2xs uppercase tracking-wide text-ink/40"
            >
              Passphrase
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
              className="mt-1.5 w-full rounded-bento border border-ink/15 bg-sand px-3.5 py-2.5 font-mono text-sm text-ink outline-none transition-colors placeholder:text-ink/25 focus:border-azure/70 disabled:opacity-50"
            />
          </div>

          {/* Announced, not just coloured -- a screen reader has to hear a
              failed sign-in, and role="alert" is what makes that happen. */}
          {error && (
            <p role="alert" className="font-mono text-2xs text-coral">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="btn-primary w-full !py-2.5 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {busy ? 'Verifying…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 font-mono text-2xs leading-relaxed text-ink/30">
          Sessions are server-side and expire after 12 hours. Signing out ends
          the session immediately.
        </p>
      </div>
    </main>
  )
}
