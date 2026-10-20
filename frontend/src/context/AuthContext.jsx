import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authApi, tokenStore, UNAUTHORIZED_EVENT } from '../api/client';

const AuthContext = createContext(null);

/**
 * Holds the signed-in account for the whole app.
 *
 * The token is the only identity the backend accepts - it derives the actor
 * recorded in the audit chain from the token's verified subject, and ignores
 * anything the client claims about who it is. So there is nothing useful to
 * keep here beyond the token and the account it resolves to.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // `loading` starts true only when there is a stored token worth checking;
  // otherwise the sign-in screen should render immediately.
  const [loading, setLoading] = useState(() => Boolean(tokenStore.get()));

  // Re-hydrate a stored session on first load. A token that no longer works
  // (expired, or the account was deactivated) is discarded silently.
  useEffect(() => {
    let cancelled = false;
    if (!tokenStore.get()) return undefined;

    authApi
      .me()
      .then((account) => {
        if (!cancelled) setUser(account);
      })
      .catch(() => {
        tokenStore.clear();
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // The API client fires this when it sees a token get rejected mid-session.
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = useCallback(async (email, password) => {
    const session = await authApi.login(email, password);
    tokenStore.set(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  /** Verifying an emailed code also signs the new account in. */
  const verifyEmail = useCallback(async (email, code) => {
    const session = await authApi.verifyEmail(email, code);
    tokenStore.set(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      verifyEmail,
      isAuthenticated: Boolean(user),
    }),
    [user, loading, login, logout, verifyEmail],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
