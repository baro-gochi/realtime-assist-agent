/**
 * @fileoverview Frontend Logger Utility
 *
 * @description
 * 환경에 따라 로그 레벨을 제어하고, 개발 환경에서는 백엔드로 로그를 전송합니다.
 * development 환경에서는 모든 로그를, production에서는 warn/error만 출력합니다.
 *
 * @example
 * import logger from './logger';
 * logger.debug('Debug message');  // development에서만 출력
 * logger.info('Info message');    // development에서만 출력
 * logger.warn('Warning');         // 항상 출력
 * logger.error('Error');          // 항상 출력
 */

const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
  NONE: 4,
};

// 환경 설정
const ENV = import.meta.env.MODE || 'development';
const LOG_LEVEL_ENV = import.meta.env.VITE_LOG_LEVEL;
const API_URL = import.meta.env.VITE_API_URL || '';

// 백엔드 로그 전송 설정 (개발 환경에서만, 명시적으로 활성화 필요)
const LOG_TO_BACKEND = import.meta.env.VITE_LOG_TO_BACKEND === 'true' && ENV !== 'production';
const LOG_BATCH_SIZE = 10; // 배치 크기
const LOG_FLUSH_INTERVAL = 5000; // 5초마다 flush

function getLogLevel() {
  if (LOG_LEVEL_ENV) {
    return LOG_LEVELS[LOG_LEVEL_ENV.toUpperCase()] ?? LOG_LEVELS.INFO;
  }
  return ENV === 'production' ? LOG_LEVELS.WARN : LOG_LEVELS.DEBUG;
}

const currentLevel = getLogLevel();

// 로그 버퍼 (백엔드 전송용)
let logBuffer = [];
let flushTimer = null;

/**
 * 로그를 백엔드로 전송
 */
async function flushLogs() {
  if (!LOG_TO_BACKEND || logBuffer.length === 0) return;

  const logsToSend = [...logBuffer];
  logBuffer = [];

  try {
    const response = await fetch(`${API_URL}/api/logs/frontend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ logs: logsToSend }),
    });

    if (!response.ok) {
      // 실패 시 콘솔에만 출력 (무한 루프 방지)
      console.warn('[Logger] Failed to send logs to backend:', response.status);
    }
  } catch {
    // 네트워크 오류 시 무시 (개발 중 서버 미실행 상황)
  }
}

/**
 * 로그를 버퍼에 추가
 */
function addToBuffer(level, message) {
  if (!LOG_TO_BACKEND) return;

  logBuffer.push({
    level,
    message: typeof message === 'string' ? message : JSON.stringify(message),
    timestamp: new Date().toISOString(),
  });

  // 배치 크기 도달 시 즉시 전송
  if (logBuffer.length >= LOG_BATCH_SIZE) {
    flushLogs();
  }
}

/**
 * 인자들을 문자열로 변환
 */
function argsToString(args) {
  return args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      if (arg instanceof Error) return `${arg.name}: ${arg.message}`;
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

/**
 * 로거 객체
 */
const logger = {
  debug: (...args) => {
    if (currentLevel <= LOG_LEVELS.DEBUG) {
      console.log('[DEBUG]', ...args);
      addToBuffer('DEBUG', argsToString(args));
    }
  },

  info: (...args) => {
    if (currentLevel <= LOG_LEVELS.INFO) {
      console.log('[INFO]', ...args);
      addToBuffer('INFO', argsToString(args));
    }
  },

  warn: (...args) => {
    if (currentLevel <= LOG_LEVELS.WARN) {
      console.warn('[WARN]', ...args);
      addToBuffer('WARN', argsToString(args));
    }
  },

  error: (...args) => {
    if (currentLevel <= LOG_LEVELS.ERROR) {
      console.error('[ERROR]', ...args);
      addToBuffer('ERROR', argsToString(args));
    }
  },

  getLevel: () => {
    const levelNames = Object.entries(LOG_LEVELS);
    const current = levelNames.find(([, v]) => v === currentLevel);
    return current ? current[0] : 'UNKNOWN';
  },

  /**
   * 버퍼의 로그를 즉시 전송 (페이지 언로드 전 호출)
   */
  flush: () => flushLogs(),
};

// 주기적 flush 타이머 설정 (백엔드 전송 활성화 시)
if (LOG_TO_BACKEND) {
  flushTimer = setInterval(flushLogs, LOG_FLUSH_INTERVAL);

  // 페이지 언로드 시 남은 로그 전송
  window.addEventListener('beforeunload', () => {
    if (flushTimer) clearInterval(flushTimer);
    // sendBeacon 사용 (비동기 요청이 차단되지 않도록)
    if (logBuffer.length > 0) {
      const data = JSON.stringify({ logs: logBuffer });
      navigator.sendBeacon(`${API_URL}/api/logs/frontend`, data);
    }
  });
}

// 초기화 메시지
if (ENV !== 'production') {
  const backendStatus = LOG_TO_BACKEND ? 'enabled' : 'disabled';
  console.log(`[Logger] Initialized: level=${logger.getLevel()}, env=${ENV}, backend=${backendStatus}`);
}

export default logger;
