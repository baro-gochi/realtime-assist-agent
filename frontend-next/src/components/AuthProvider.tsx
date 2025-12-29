"use client";

/**
 * AuthProvider - 인증 상태 관리
 *
 * 기존 Vite+React 프로젝트의 인증 로직을 Next.js App Router용으로 변환
 * - sessionStorage에서 토큰 로드
 * - 서버에서 토큰 유효성 검증
 * - 인증 상태 전역 관리
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  authToken: string | null;
  login: (password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 토큰 검증 함수
  const verifyToken = useCallback(async (token: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "bypass-tunnel-reminder": "true",
          "ngrok-skip-browser-warning": "true",
        },
        body: `password=${encodeURIComponent(token)}`,
      });
      return response.ok;
    } catch {
      return false;
    }
  }, []);

  // 초기 인증 상태 확인 (클라이언트에서만 실행)
  useEffect(() => {
    const checkAuth = async () => {
      const savedToken = sessionStorage.getItem("auth_token");
      if (savedToken) {
        const isValid = await verifyToken(savedToken);
        if (isValid) {
          setAuthToken(savedToken);
        } else {
          sessionStorage.removeItem("auth_token");
        }
      }
      setIsLoading(false);
    };

    checkAuth();
  }, [verifyToken]);

  // 로그인 함수
  const login = useCallback(
    async (password: string): Promise<{ success: boolean; error?: string }> => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "bypass-tunnel-reminder": "true",
            "ngrok-skip-browser-warning": "true",
          },
          body: `password=${encodeURIComponent(password)}`,
        });

        if (response.ok) {
          sessionStorage.setItem("auth_token", password);
          setAuthToken(password);
          return { success: true };
        } else {
          const data = await response.json();
          return { success: false, error: data.detail || "인증 실패" };
        }
      } catch {
        return {
          success: false,
          error: "서버 연결 실패. 백엔드가 실행 중인지 확인하세요.",
        };
      }
    },
    []
  );

  // 로그아웃 함수
  const logout = useCallback(() => {
    sessionStorage.removeItem("auth_token");
    setAuthToken(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!authToken,
        isLoading,
        authToken,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
