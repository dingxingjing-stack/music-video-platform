import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';

interface UserInfo { id: string; email: string; username: string; }
interface AuthCtx { user: UserInfo | null; isLoggedIn: boolean; login: (email: string, pwd: string) => Promise<void>; logout: () => void; showLogin: boolean; setShowLogin: (v: boolean) => void; }

const Ctx = createContext<AuthCtx>(null!);
const USER_KEY = 'zyvexo_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(() => {
    const s = localStorage.getItem(USER_KEY);
    return s ? JSON.parse(s) : null;
  });
  const [showLogin, setShowLogin] = useState(false);

  const login = useCallback(async (email: string, _pwd: string) => {
    const id = 'user_' + Date.now().toString(36);
    const u: UserInfo = { id, email, username: email.split('@')[0] };
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    setUser(u);
    setShowLogin(false);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(USER_KEY);
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, isLoggedIn: !!user, login, logout, showLogin, setShowLogin }}>{children}</Ctx.Provider>;
}

export function useAuth() { return useContext(Ctx); }