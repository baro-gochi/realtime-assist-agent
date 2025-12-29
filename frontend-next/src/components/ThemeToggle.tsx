"use client";

/**
 * ThemeToggle - 테마 전환 버튼
 *
 * 다크/라이트 모드 전환 버튼 (기존 프로젝트의 ThemeToggleButton 변환)
 */

import { useContext } from "react";
import { ThemeContext } from "./ThemeProvider";

export function ThemeToggle() {
  const context = useContext(ThemeContext);

  // SSR 중이거나 ThemeProvider 외부에서 렌더링 시 숨김
  if (!context) {
    return null;
  }

  const { isDarkMode, toggleTheme } = context;

  return (
    <button
      onClick={toggleTheme}
      title={isDarkMode ? "라이트 모드" : "다크 모드"}
      className="fixed top-5 right-5 z-50 flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-border-primary bg-bg-card text-text-secondary shadow-sm transition-all hover:border-primary hover:bg-primary hover:text-white"
    >
      {isDarkMode ? (
        // Sun icon (라이트 모드로 전환)
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      ) : (
        // Moon icon (다크 모드로 전환)
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  );
}
