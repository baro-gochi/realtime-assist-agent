"use client";

/**
 * Providers - Client-side providers wrapper
 *
 * 모든 클라이언트 사이드 프로바이더를 하나로 묶어서 관리
 * Next.js App Router에서 Server Component인 layout.tsx에서 사용
 */

import { type ReactNode } from "react";
import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";
import { AuthProvider } from "./AuthProvider";

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <AuthProvider>
      <ThemeProvider>
        <ThemeToggle />
        {children}
      </ThemeProvider>
    </AuthProvider>
  );
}
