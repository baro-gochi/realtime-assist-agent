"use client";

/**
 * @fileoverview 통화 시간 타이머 훅
 */

import { useState, useEffect, useRef, useCallback } from 'react';

interface UseCallTimerReturn {
  /** 통화 시간 (초) */
  duration: number;
  /** 통화 시작 시간 */
  startTime: number | null;
  /** 타이머 시작 */
  start: () => void;
  /** 타이머 정지 */
  stop: () => void;
  /** 타이머 리셋 */
  reset: () => void;
  /** 포맷된 시간 문자열 */
  formatted: string;
}

export function useCallTimer(): UseCallTimerReturn {
  const [duration, setDuration] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(() => {
    if (timerRef.current) return; // 이미 실행 중

    const now = Date.now();
    setStartTime(now);
    setDuration(0);

    timerRef.current = setInterval(() => {
      setDuration(Math.floor((Date.now() - now) / 1000));
    }, 1000);
  }, []);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stop();
    setDuration(0);
    setStartTime(null);
  }, [stop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  // Format duration
  const formatted = (() => {
    const hours = Math.floor(duration / 3600);
    const minutes = Math.floor((duration % 3600) / 60);
    const secs = duration % 60;

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  })();

  return {
    duration,
    startTime,
    start,
    stop,
    reset,
    formatted,
  };
}
