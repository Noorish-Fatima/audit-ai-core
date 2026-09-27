'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { clearAuth, setAccessToken, setAuthInit } from '@/lib/api';

interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      // Skip the probe entirely when we know there's no session (avoids a
      // noisy 401 in the console for anonymous visitors).
      if (typeof window !== 'undefined' && !localStorage.getItem('audit-ai-session')) {
        setUser(null);
        return;
      }
      // Restore the in-memory access token first via the httpOnly refresh
      // cookie, so subsequent API calls authenticate on the first attempt
      // instead of 401ing and recovering through the refresh interceptor.
      const refresh = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      });
      if (!refresh.ok) {
        setUser(null);
        if (typeof window !== 'undefined') localStorage.removeItem('audit-ai-session');
        return;
      }
      const { access_token } = await refresh.json();
      if (access_token) {
        setAccessToken(access_token);
      }
      const response = await fetch('/api/v1/auth/me', {
        headers: access_token ? { Authorization: `Bearer ${access_token}` } : {},
        credentials: 'include',
      });
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Register the restore promise so API calls started during page load
    // wait for the token before firing (prevents 401-then-retry noise).
    setAuthInit(refreshUser());
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    // Store the access token in memory for the API client (avoids a
    // pointless 401 + refresh round-trip on the first authenticated call)
    if (data.access_token) {
      setAccessToken(data.access_token);
    }
    // User data is returned in the response
    setUser(data.user);
    if (typeof window !== 'undefined') localStorage.setItem('audit-ai-session', '1');
  };

  const logout = () => {
    // Call logout endpoint to clear refresh token cookie
    fetch('/api/v1/auth/logout', {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {});

    // Clear local state
    clearAuth();
    if (typeof window !== 'undefined') localStorage.removeItem('audit-ai-session');
    setUser(null);
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};