"use client";

/**
 * Agent History Page
 *
 * 상담 이력 조회 페이지 (기존 AgentHistory.jsx 마이그레이션)
 */

import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";

export default function AgentHistoryPage() {
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
              href="/agent/register"
              className="text-text-secondary hover:text-primary"
            >
              Register
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 p-6">
        <div className="mx-auto max-w-4xl">
          <h1 className="mb-6 text-2xl font-bold text-text-primary">
            Consultation History
          </h1>

          {/* Search Bar */}
          <div className="mb-6 flex gap-4">
            <input
              type="text"
              placeholder="Search by customer name or phone..."
              className="flex-1 rounded-lg border border-border-primary bg-bg-card px-4 py-3 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none"
            />
            <button className="rounded-lg bg-primary px-6 py-3 font-medium text-white transition-colors hover:bg-primary-hover">
              Search
            </button>
          </div>

          {/* History Table Placeholder */}
          <div className="overflow-hidden rounded-xl border border-border-primary bg-bg-card">
            <table className="w-full">
              <thead className="border-b border-border-primary bg-bg-secondary">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                    Customer
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                    Agent
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                    Duration
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-text-secondary">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border-primary">
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-text-muted"
                  >
                    No consultation history found. Start a consultation to see
                    records here.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
    </AuthGuard>
  );
}
