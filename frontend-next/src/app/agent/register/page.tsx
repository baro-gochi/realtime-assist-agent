"use client";

/**
 * Agent Register Page
 *
 * 상담사 등록 페이지 (기존 AgentRegister.jsx 마이그레이션)
 */

import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";

export default function AgentRegisterPage() {
  return (
    <AuthGuard>
    <div className="flex min-h-screen flex-col bg-bg-primary">
      {/* Header */}
      <header className="border-b border-border-primary bg-bg-card px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <Link href="/" className="text-xl font-bold text-text-primary">
            Realtime Assist Agent
          </Link>
          <nav className="flex gap-4">
            <Link
              href="/assistant"
              className="text-text-secondary hover:text-primary"
            >
              Dashboard
            </Link>
            <Link
              href="/agent/history"
              className="text-text-secondary hover:text-primary"
            >
              History
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-md rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
          <h1 className="mb-6 text-center text-2xl font-bold text-text-primary">
            Agent Registration
          </h1>

          {/* Registration Form Placeholder */}
          <form className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-text-primary">
                Agent Name
              </label>
              <input
                type="text"
                placeholder="Enter agent name"
                className="w-full rounded-lg border border-border-primary bg-bg-secondary px-4 py-3 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-text-primary">
                Agent Code
              </label>
              <input
                type="text"
                placeholder="Enter agent code"
                className="w-full rounded-lg border border-border-primary bg-bg-secondary px-4 py-3 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-text-primary">
                Department
              </label>
              <input
                type="text"
                placeholder="Enter department"
                className="w-full rounded-lg border border-border-primary bg-bg-secondary px-4 py-3 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none"
              />
            </div>

            <button
              type="submit"
              className="w-full rounded-lg bg-primary py-3 font-medium text-white transition-colors hover:bg-primary-hover"
            >
              Register Agent
            </button>
          </form>
        </div>
      </main>
    </div>
    </AuthGuard>
  );
}
