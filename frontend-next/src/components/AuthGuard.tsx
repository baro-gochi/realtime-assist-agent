"use client";

/**
 * AuthGuard - 인증이 필요한 컨텐츠 보호
 *
 * 인증되지 않은 사용자에게는 PasswordScreen을 표시하고,
 * 인증된 사용자에게는 children을 렌더링합니다.
 */

import { type ReactNode } from "react";
import { useAuth } from "./AuthProvider";
import { PasswordScreen } from "./PasswordScreen";

interface AuthGuardProps {
  children: ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();

  // 로딩 중
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary">
        <div className="text-center">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
          <p className="text-text-secondary">인증 확인 중...</p>
        </div>
      </div>
    );
  }

  // 인증되지 않은 경우 비밀번호 화면 표시
  if (!isAuthenticated) {
    return <PasswordScreen />;
  }

  // 인증된 경우 children 렌더링
  return <>{children}</>;
}
