import Link from "next/link";

/**
 * Home Page - AI Consultation Assistant Dashboard
 *
 * 메인 페이지: 역할 선택 및 상담 시작
 * TailwindCSS 유틸리티 클래스 사용
 */
export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary">
      <main className="w-full max-w-md px-6">
        {/* Welcome Card */}
        <div className="rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
          <h1 className="mb-2 text-center text-2xl font-bold text-text-primary">
            Realtime Assist Agent
          </h1>
          <p className="mb-8 text-center text-text-secondary">
            AI-powered real-time consultation assistant
          </p>

          {/* Navigation Links */}
          <div className="flex flex-col gap-4">
            <Link
              href="/assistant"
              className="flex h-12 items-center justify-center rounded-lg bg-primary text-white transition-colors hover:bg-primary-hover"
            >
              Start Consultation
            </Link>

            <Link
              href="/agent/register"
              className="flex h-12 items-center justify-center rounded-lg border border-border-primary bg-bg-secondary text-text-primary transition-colors hover:border-primary hover:text-primary"
            >
              Agent Registration
            </Link>

            <Link
              href="/agent/history"
              className="flex h-12 items-center justify-center rounded-lg border border-border-primary bg-bg-secondary text-text-primary transition-colors hover:border-primary hover:text-primary"
            >
              Consultation History
            </Link>
          </div>
        </div>

        {/* Tech Stack Info */}
        <div className="mt-6 text-center text-sm text-text-muted">
          <p>Next.js 16.1 + React 19 + TailwindCSS 4</p>
        </div>
      </main>
    </div>
  );
}
