import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { clearToken, fetchMe, getToken, guestLogin, setToken, type UserInfo } from "../lib/api";

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  signIn: (tokens: { access_token: string }) => Promise<void>;
  signInAsGuest: () => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  signIn: async () => {},
  signInAsGuest: async () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    if (!getToken()) { setLoading(false); return; }
    try {
      const me = await fetchMe();
      setUser(me);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUser(); }, [loadUser]);

  const signIn = useCallback(async (tokens: { access_token: string }) => {
    setToken(tokens.access_token);
    const me = await fetchMe();
    setUser(me);
  }, []);

  const signInAsGuest = useCallback(async () => {
    const tokens = await guestLogin();
    setToken(tokens.access_token);
    const me = await fetchMe();
    setUser(me);
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signInAsGuest, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
