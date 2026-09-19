import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

interface AuthCtx {
  user: User | null;
  session: Session | null;
  isLoggedIn: boolean;
  loading: boolean;
  login: (email: string, pwd: string) => Promise<void>;
  register: (email: string, pwd: string) => Promise<{ needsEmailConfirmation: boolean }>;
  resendVerification: (email: string) => Promise<void>;
  sendPhoneOtp: (phone: string) => Promise<void>;
  verifyPhoneOtp: (phone: string, otp: string) => Promise<void>;
  logout: () => Promise<void>;
  showLogin: boolean;
  setShowLogin: (v: boolean) => void;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true); // 初始 getSession 完成前为 true
  const [showLogin, setShowLogin] = useState(false);

  // 初始恢复 session + 订阅 auth 状态变化（含 TOKEN_REFRESHED / SIGNED_IN / SIGNED_OUT）
  useEffect(() => {
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session ?? null);
      setUser(data.session?.user ?? null);
      setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession ?? null);
      setUser(newSession?.user ?? null);
      setLoading(false);
    });

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const login = useCallback(async (email: string, pwd: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password: pwd });
    if (error) throw error;
    setShowLogin(false);
  }, []);

  const register = useCallback(async (email: string, pwd: string) => {
    const { data, error } = await supabase.auth.signUp({ email, password: pwd });
    if (error) throw error;
    // 情况 A：signUp 即登录（无邮箱验证）→ session 存在；onAuthStateChange 会自动置 session/user。
    // 情况 B：需邮箱验证 → session 为 null（不是失败）。
    return { needsEmailConfirmation: !data.session };
  }, []);

  const resendVerification = useCallback(async (email: string) => {
    const { error } = await supabase.auth.resend({ type: 'signup', email });
    if (error) throw error;
  }, []);

  const sendPhoneOtp = useCallback(async (phone: string) => {
    // Supabase Phone Auth 负责创建/复用 Auth 用户；signup/signin 由同一个 OTP 流程完成。
    const { error } = await supabase.auth.signInWithOtp({ phone });
    if (error) throw error;
  }, []);

  const verifyPhoneOtp = useCallback(async (phone: string, otp: string) => {
    const { data, error } = await supabase.auth.verifyOtp({ phone, token: otp, type: 'sms' });
    if (error) throw error;
    if (!data.session) throw new Error('Phone verification did not create a session');
    setShowLogin(false);
  }, []);

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
    setShowLogin(false);
  }, []);

  const value: AuthCtx = {
    user,
    session,
    isLoggedIn: !!session?.user,
    loading,
    login,
    register,
    resendVerification,
    sendPhoneOtp,
    verifyPhoneOtp,
    logout,
    showLogin,
    setShowLogin,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
