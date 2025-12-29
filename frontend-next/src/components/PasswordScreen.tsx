"use client";

/**
 * PasswordScreen - 비밀번호 입력 화면
 *
 * 기존 Vite+React 프로젝트의 PasswordScreen을 Next.js + TailwindCSS로 변환
 */

import { useState, type FormEvent } from "react";
import { useAuth } from "./AuthProvider";

export function PasswordScreen() {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const result = await login(password);

    if (!result.success) {
      setError(result.error || "인증 실패");
    }
    setLoading(false);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-4">
      <div className="w-full max-w-md rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
        <h1 className="mb-2 text-center text-2xl font-bold text-text-primary">
          실시간 상담 어시스턴트
        </h1>
        <p className="mb-6 text-center text-sm text-text-secondary">
          접근하려면 비밀번호를 입력하세요
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 입력"
            autoFocus
            className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-3 text-text-primary placeholder-text-muted outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
          />

          {error && (
            <p className="text-center text-sm text-status-error">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-lg bg-primary px-4 py-3 font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "확인 중..." : "로그인"}
          </button>
        </form>
      </div>
    </div>
  );
}
