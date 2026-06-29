import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { clearToken, fetchMe, getToken, setToken, type UserInfo } from "./api";

const GUEST_USER: UserInfo = {
  user_id: "guest",
  org_id: "demo",
  email: "guest@demo",
  role: "safety_officer",
  is_active: true,
  created_at: new Date().toISOString(),
};

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  signIn: (tokens: { access_token: string }) => Promise<void>;
  signInAsGuest: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  signIn: async () => {},
  signInAsGuest: () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    if (localStorage.getItem("safesight_guest")) {
      setUser(GUEST_USER);
      setLoading(false);
      return;
    }
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

  const signInAsGuest = useCallback(() => {
    localStorage.setItem("safesight_guest", "1");
    setUser(GUEST_USER);
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    localStorage.removeItem("safesight_guest");
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
