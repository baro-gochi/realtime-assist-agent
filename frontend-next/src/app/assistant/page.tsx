"use client";

/**
 * Assistant Page - AI Consultation Dashboard
 *
 * WebRTC, STT, AI Agent integration for real-time consultation
 */

import { AuthGuard } from "@/components/AuthGuard";
import { AssistantMain } from "@/components/assistant";

export default function AssistantPage() {
  return (
    <AuthGuard>
      <AssistantMain />
    </AuthGuard>
  );
}
