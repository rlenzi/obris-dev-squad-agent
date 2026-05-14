import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { clearToken, fetchMe, getToken, setToken, type MeResponse } from './api';

interface AuthContextValue {
  me: MeResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setLocalToken] = useState<string | null>(() => getToken());

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    enabled: Boolean(token),
    retry: false,
  });

  // Quando token muda no localStorage por outra aba/window
  useEffect(() => {
    const handler = () => setLocalToken(getToken());
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  const value: AuthContextValue = {
    me: meQuery.data ?? null,
    isLoading: Boolean(token) && meQuery.isLoading,
    isAuthenticated: Boolean(token) && Boolean(meQuery.data),
    loginWithToken: async (newToken: string) => {
      setToken(newToken);
      setLocalToken(newToken);
      await meQuery.refetch();
    },
    logout: () => {
      clearToken();
      setLocalToken(null);
      window.location.href = '/login';
    },
    refresh: async () => {
      await meQuery.refetch();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth deve ser usado dentro de AuthProvider');
  }
  return ctx;
}
