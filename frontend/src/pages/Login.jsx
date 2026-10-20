import { useState } from 'react';
import { ArrowLeft, KeyRound, LogIn, MailCheck, ShieldCheck, UserPlus } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { authApi } from '../api/client';
import ErrorMessage from '../components/ErrorMessage';
import { cx } from '../utils/formatters';

/**
 * Demo accounts, created by `python scripts/seed_users.py`.
 *
 * Shown on the sign-in screen on purpose: these are prototype credentials for
 * synthetic data, and an evaluator opening this for the first time would
 * otherwise have no way in.
 */
const DEMO_ACCOUNTS = [
  { email: 'supervisor@kone-elevate.demo', role: 'Supervisor', can: 'Everything, plus provisioning accounts' },
  { email: 'technician@kone-elevate.demo', role: 'Technician', can: 'Register components, log service, run assessments' },
  { email: 'planner@kone-elevate.demo', role: 'Recovery planner', can: 'Component-recovery capacity planning and forecasts' },
  { email: 'sustainability@kone-elevate.demo', role: 'Sustainability controller', can: 'ESRS/BRSR reporting, anchors the audit chain' },
  { email: 'auditor@kone-elevate.demo', role: 'Read-only auditor', can: 'Sees everything, can change nothing' },
];

const DEMO_PASSWORD = 'elevate-demo-2026';
const MIN_PASSWORD_LENGTH = 12;

export default function Login() {
  const { login, verifyEmail } = useAuth();
  const [mode, setMode] = useState('signin'); // signin | signup | verify

  // Shared across modes so switching tabs keeps what was typed.
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [code, setCode] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const run = async (action) => {
    setSubmitting(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const submitSignIn = (event) => {
    event.preventDefault();
    run(() => login(email.trim(), password));
  };

  const submitSignUp = (event) => {
    event.preventDefault();
    run(async () => {
      const result = await authApi.signup({
        email: email.trim(),
        display_name: displayName.trim(),
        password,
      });
      setNotice(result);
      setCode('');
      setMode('verify');
    });
  };

  const submitVerify = (event) => {
    event.preventDefault();
    run(() => verifyEmail(email.trim(), code.trim()));
  };

  const resend = () =>
    run(async () => {
      const result = await authApi.resendCode(email.trim());
      setNotice(result);
    });

  const switchMode = (next) => {
    setMode(next);
    setError(null);
    if (next !== 'verify') setNotice(null);
  };

  const fillDemoAccount = (demoEmail) => {
    setMode('signin');
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError(null);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4 py-10">
      <div className="w-full max-w-4xl overflow-hidden rounded-2xl bg-white shadow-elevated md:grid md:grid-cols-5">
        {/* ---------------------------------------------------------- form */}
        <div className="p-8 md:col-span-2">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent font-extrabold text-white">
              KE
            </span>
            <div>
              <p className="text-sm font-extrabold uppercase tracking-widest text-navy-900">
                KONE ELEVATE
              </p>
              <p className="text-[0.65rem] uppercase tracking-wider text-steel-500">
                Component Passport
              </p>
            </div>
          </div>

          {mode === 'verify' ? (
            <VerifyPanel
              email={email}
              code={code}
              setCode={setCode}
              notice={notice}
              error={error}
              submitting={submitting}
              onSubmit={submitVerify}
              onResend={resend}
              onBack={() => switchMode('signup')}
            />
          ) : (
            <>
              <div className="mt-7 flex gap-1 border-b border-steel-200">
                <TabButton active={mode === 'signin'} onClick={() => switchMode('signin')}>
                  Sign in
                </TabButton>
                <TabButton active={mode === 'signup'} onClick={() => switchMode('signup')}>
                  Create account
                </TabButton>
              </div>

              <p className="mt-4 text-sm text-steel-500">
                {mode === 'signin'
                  ? 'Every change you make is recorded against this account in the audit chain.'
                  : 'We will email you a code to confirm the address before the account works.'}
              </p>

              <form
                onSubmit={mode === 'signin' ? submitSignIn : submitSignUp}
                className="mt-5 space-y-4"
              >
                {error ? <ErrorMessage error={error} compact /> : null}

                {mode === 'signup' ? (
                  <div>
                    <label className="label" htmlFor="signup-name">
                      Your name
                    </label>
                    <input
                      id="signup-name"
                      autoComplete="name"
                      required
                      className="input"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      placeholder="A. Technician"
                    />
                  </div>
                ) : null}

                <div>
                  <label className="label" htmlFor="login-email">
                    Email
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    autoComplete="username"
                    required
                    className="input"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@kone-elevate.demo"
                  />
                </div>

                <div>
                  <label className="label" htmlFor="login-password">
                    Password
                  </label>
                  <input
                    id="login-password"
                    type="password"
                    autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                    required
                    minLength={mode === 'signup' ? MIN_PASSWORD_LENGTH : undefined}
                    className="input"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                  {mode === 'signup' ? (
                    <p className="mt-1 text-[0.7rem] text-steel-400">
                      At least {MIN_PASSWORD_LENGTH} characters.
                    </p>
                  ) : null}
                </div>

                <button type="submit" className="btn-accent w-full" disabled={submitting}>
                  {mode === 'signin' ? (
                    <LogIn className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <UserPlus className="h-4 w-4" aria-hidden="true" />
                  )}
                  {submitting
                    ? 'Working...'
                    : mode === 'signin'
                      ? 'Sign in'
                      : 'Create account'}
                </button>
              </form>

              {mode === 'signup' ? (
                <p className="mt-4 rounded-lg bg-steel-50 px-3 py-2.5 text-[0.7rem] leading-relaxed text-steel-600">
                  New accounts get <strong className="text-navy-800">technician</strong> access.
                  Confirming an email proves you own the address — it does not decide what you
                  are allowed to do, so anything above that is granted by a supervisor.
                </p>
              ) : null}

              <p className="mt-5 flex gap-2 text-[0.7rem] leading-relaxed text-steel-400">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  Local authentication against this platform&apos;s own account table.
                  Production would use company single sign-on (Entra ID); this build has no
                  tenant to authenticate against.
                </span>
              </p>
            </>
          )}
        </div>

        {/* -------------------------------------------------- demo accounts */}
        <div className="border-t border-steel-200 bg-steel-50 p-8 md:col-span-3 md:border-l md:border-t-0">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-steel-500" aria-hidden="true" />
            <h2 className="text-sm font-bold text-navy-900">Demo accounts</h2>
          </div>
          <p className="mt-1 text-xs text-steel-500">
            Pre-made accounts covering all five permission levels. Click one to fill the sign-in
            form. Password for all five:{' '}
            <code className="rounded bg-white px-1.5 py-0.5 font-mono text-[0.7rem] text-navy-800">
              {DEMO_PASSWORD}
            </code>
          </p>

          <ul className="mt-4 space-y-2">
            {DEMO_ACCOUNTS.map((account) => (
              <li key={account.email}>
                <button
                  type="button"
                  onClick={() => fillDemoAccount(account.email)}
                  className="w-full rounded-lg border border-steel-200 bg-white px-3 py-2.5 text-left transition-colors hover:border-accent hover:bg-cyan-50/40"
                >
                  <span className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-semibold text-navy-900">{account.role}</span>
                    <span className="font-mono text-[0.7rem] text-steel-500">{account.email}</span>
                  </span>
                  <span className="mt-0.5 block text-xs text-steel-500">{account.can}</span>
                </button>
              </li>
            ))}
          </ul>

          <p className="mt-4 text-[0.7rem] leading-relaxed text-steel-400">
            Not seeing these? Run{' '}
            <code className="font-mono">python scripts/seed_users.py</code> in{' '}
            <code className="font-mono">backend/</code>.
          </p>
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        '-mb-px border-b-2 px-4 py-2 text-sm font-semibold transition-colors',
        active
          ? 'border-accent text-navy-900'
          : 'border-transparent text-steel-500 hover:text-navy-700',
      )}
    >
      {children}
    </button>
  );
}

/**
 * Code entry.
 *
 * `delivery_mode` matters: with no mail server configured the backend writes
 * the code to its log instead of sending it, and saying "check your inbox"
 * would send the user looking for an email that is never going to arrive.
 */
function VerifyPanel({ email, code, setCode, notice, error, submitting, onSubmit, onResend, onBack }) {
  const wentToOutbox = notice?.delivery_mode === 'outbox';

  return (
    <>
      <button
        type="button"
        onClick={onBack}
        className="mt-7 flex items-center gap-1.5 text-xs font-semibold text-steel-500 hover:text-navy-800"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Back
      </button>

      <h1 className="mt-3 flex items-center gap-2 text-xl font-extrabold text-navy-900">
        <MailCheck className="h-5 w-5 text-accent" aria-hidden="true" />
        Confirm your email
      </h1>
      <p className="mt-1 break-all text-sm text-steel-500">
        Enter the code for <strong className="text-navy-800">{email}</strong>.
      </p>

      {notice ? (
        <div
          className={cx(
            'mt-4 rounded-lg border px-3 py-2.5 text-xs leading-relaxed',
            wentToOutbox
              ? 'border-amber-200 bg-amber-50 text-amber-900'
              : 'border-emerald-200 bg-emerald-50 text-emerald-900',
          )}
        >
          {notice.message}
          {wentToOutbox ? (
            <span className="mt-1 block text-[0.7rem]">
              Look for a line beginning <code className="font-mono">---- message for</code> in
              the backend terminal, or open the newest file in{' '}
              <code className="font-mono">backend/data/outbox/</code>.
            </span>
          ) : null}
        </div>
      ) : null}

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        {error ? <ErrorMessage error={error} compact /> : null}

        <div>
          <label className="label" htmlFor="verify-code">
            Verification code
          </label>
          <input
            id="verify-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            className="input text-center font-mono text-lg tracking-[0.5em]"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="000000"
          />
          {notice?.code_expires_in_minutes ? (
            <p className="mt-1 text-[0.7rem] text-steel-400">
              Expires in {notice.code_expires_in_minutes} minutes. Single use.
            </p>
          ) : null}
        </div>

        <button type="submit" className="btn-accent w-full" disabled={submitting}>
          <MailCheck className="h-4 w-4" aria-hidden="true" />
          {submitting ? 'Checking...' : 'Verify and sign in'}
        </button>
      </form>

      <button
        type="button"
        onClick={onResend}
        disabled={submitting}
        className="mt-3 w-full text-xs font-semibold text-accent hover:underline disabled:opacity-50"
      >
        Send a new code
      </button>
    </>
  );
}
