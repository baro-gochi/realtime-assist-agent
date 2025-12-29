"use client";

/**
 * ThemeProvider - 다크/라이트 모드 관리
 *
 * 기존 Vite+React 프로젝트의 테마 로직을 Next.js App Router용으로 변환
 * - localStorage에서 테마 설정 로드
 * - 시스템 설정 감지 (prefers-color-scheme)
 * - data-theme 속성으로 테마 적용
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export interface ThemeContextType {
  isDarkMode: boolean;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [mounted, setMounted] = useState(false);

  // 초기 테마 설정 (클라이언트에서만 실행)
  useEffect(() => {
    const saved = localStorage.getItem("darkMode");
    if (saved !== null) {
      setIsDarkMode(saved === "true");
    } else {
      // localStorage에 저장된 값이 없으면 시스템 설정 따라감
      setIsDarkMode(window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
    setMounted(true);
  }, []);

  // 테마 변경 시 localStorage 저장 및 document 속성 설정
  useEffect(() => {
    if (mounted) {
      localStorage.setItem("darkMode", String(isDarkMode));
      document.documentElement.setAttribute(
        "data-theme",
        isDarkMode ? "dark" : "light"
      );
    }
  }, [isDarkMode, mounted]);

  // 시스템 설정 변경 감지
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e: MediaQueryListEvent) => {
      // localStorage에 저장된 값이 없을 때만 시스템 설정 따라감
      if (localStorage.getItem("darkMode") === null) {
        setIsDarkMode(e.matches);
      }
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  const toggleTheme = () => {
    setIsDarkMode((prev) => !prev);
  };

  // SSR 중에는 기본 테마 렌더링 (hydration mismatch 방지)
  if (!mounted) {
    return <>{children}</>;
  }

  return (
    <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
