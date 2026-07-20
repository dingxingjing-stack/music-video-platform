import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';

interface UserInfo { id: string; email: string; username: string; }
interface AuthCtx {
  user: UserInfo | null;
  isLoggedIn: boolean;
  login: (email: string, pwd: string) => Promise<void>;
  logout: () => void;
  showLogin: boolean;
  setShowLogin: (v: boolean) => void;
}

const Ctx = createContext<AuthCtx>(null!);
const USER_KEY = 'zyvexo_user';

function readUser(): UserInfo | null {
  try {
    const s = localStorage.getItem(USER_KEY);
    return s ? JSON.parse(s) as UserInfo : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(readUser);
  const [showLogin, setShowLogin] = useState(false);

  // 多标签同步：其他标签改了 localStorage 后本标签也跟着更新
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === USER_KEY) setUser(readUser());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const login = useCallback(async (email: string, _pwd: string) => {
    const id = 'user_' + Date.now().toString(36);
    const u: UserInfo = { id, email, username: email.split('@')[0] || 'user' };
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    setUser(u);
    setShowLogin(false);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(USER_KEY);
    setUser(null);
  }, []);

  return (
    <Ctx.Provider value={{ user, isLoggedIn: !!user, login, logout, showLogin, setShowLogin }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() { return useContext(Ctx); }