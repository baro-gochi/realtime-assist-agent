"use client";

/**
 * RoleSelection - 역할 선택 화면
 *
 * 상담사/고객 역할을 선택하는 초기 화면
 */

import type { UserRole } from '@/lib/types';

interface RoleSelectionProps {
  onSelectRole: (role: UserRole) => void;
}

export function RoleSelection({ onSelectRole }: RoleSelectionProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary p-6">
      <div className="w-full max-w-md rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
        <h1 className="mb-2 text-center text-2xl font-bold text-text-primary">
          실시간 상담 어시스턴트
        </h1>
        <p className="mb-8 text-center text-sm text-text-secondary">
          역할을 선택하세요
        </p>

        <div className="space-y-4">
          <button
            onClick={() => onSelectRole('agent')}
            className="flex w-full items-center gap-4 rounded-lg border border-border-primary bg-bg-secondary p-4 transition-colors hover:border-primary hover:bg-primary/5"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <svg
                className="h-6 w-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
            </div>
            <div className="flex-1 text-left">
              <h3 className="font-semibold text-text-primary">상담사</h3>
              <p className="text-sm text-text-secondary">
                상담 방을 생성하고 고객을 기다립니다
              </p>
            </div>
          </button>

          <button
            onClick={() => onSelectRole('customer')}
            className="flex w-full items-center gap-4 rounded-lg border border-border-primary bg-bg-secondary p-4 transition-colors hover:border-primary hover:bg-primary/5"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-green/10 text-accent-green">
              <svg
                className="h-6 w-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
            </div>
            <div className="flex-1 text-left">
              <h3 className="font-semibold text-text-primary">고객</h3>
              <p className="text-sm text-text-secondary">
                대기 중인 상담 방에 입장합니다
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
