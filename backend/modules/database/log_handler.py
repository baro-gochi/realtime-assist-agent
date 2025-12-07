"""데이터베이스 로그 핸들러 모듈.

Python logging을 PostgreSQL에 저장하는 커스텀 핸들러입니다.

Examples:
    >>> import logging
    >>> from modules.database import DatabaseLogHandler
    >>>
    >>> handler = DatabaseLogHandler()
    >>> logging.getLogger().addHandler(handler)
"""

import logging
import asyncio
import traceback
from typing import Optional
from queue import Queue, Empty
from threading import Thread

from .repository import SystemLogRepository


class DatabaseLogHandler(logging.Handler):
    """Python 로그를 PostgreSQL에 저장하는 핸들러.

    비동기 DB 저장을 위해 백그라운드 스레드와 큐를 사용합니다.
    로그 저장 실패 시에도 애플리케이션 동작에 영향을 주지 않습니다.

    Attributes:
        queue: 로그 레코드를 저장하는 큐
        worker_thread: 백그라운드 저장 스레드
        _stop_event: 스레드 종료 이벤트
    """

    def __init__(
        self,
        level: int = logging.INFO,
        batch_size: int = 10,
        flush_interval: float = 5.0
    ):
        """핸들러를 초기화합니다.

        Args:
            level: 최소 로그 레벨 (기본값: INFO)
            batch_size: 배치 저장 크기 (기본값: 10)
            flush_interval: 플러시 간격 초 (기본값: 5.0)
        """
        super().__init__(level)
        self.queue: Queue = Queue()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._stop_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._started = False

        # 무한 루프 방지: 자체 로거는 DB 저장하지 않음
        self._excluded_loggers = {
            "modules.database.log_handler",
            "modules.database.repository",
            "modules.database.connection",
            "asyncpg",
        }

    def emit(self, record: logging.LogRecord):
        """로그 레코드를 큐에 추가합니다.

        Args:
            record: 로그 레코드
        """
        # 무한 루프 방지
        if record.name in self._excluded_loggers:
            return

        try:
            # 큐에 레코드 추가
            self.queue.put_nowait(self._format_record(record))
        except Exception:
            # 큐 추가 실패 시 무시 (콘솔 핸들러에서 처리됨)
            pass

    def _format_record(self, record: logging.LogRecord) -> dict:
        """로그 레코드를 딕셔너리로 변환합니다.

        Args:
            record: 로그 레코드

        Returns:
            DB 저장용 딕셔너리
        """
        exception = None
        if record.exc_info:
            exception = "".join(traceback.format_exception(*record.exc_info))

        return {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger_name": record.name,
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
            "exception": exception,
            "extra": getattr(record, "extra", None),
        }

    async def start(self):
        """백그라운드 저장 태스크를 시작합니다."""
        if self._started:
            return

        self._started = True
        self._loop = asyncio.get_event_loop()
        self._task = asyncio.create_task(self._worker())

    async def stop(self):
        """백그라운드 저장 태스크를 종료합니다."""
        if not self._started:
            return

        self._stop_event.set()
        if self._task:
            await self._task
        self._started = False

    async def _worker(self):
        """백그라운드에서 로그를 DB에 저장하는 워커."""
        repo = SystemLogRepository()
        batch = []

        while not self._stop_event.is_set():
            try:
                # 큐에서 레코드 가져오기
                while len(batch) < self.batch_size:
                    try:
                        record = self.queue.get_nowait()
                        batch.append(record)
                    except Empty:
                        break

                # 배치 저장
                if batch:
                    for record in batch:
                        await repo.add_log(**record)
                    batch.clear()

                # 대기
                await asyncio.sleep(self.flush_interval)

            except Exception as e:
                # 워커 오류는 콘솔에만 출력
                print(f"DatabaseLogHandler worker error: {e}")
                await asyncio.sleep(self.flush_interval)

        # 종료 전 남은 로그 저장
        while not self.queue.empty():
            try:
                record = self.queue.get_nowait()
                await repo.add_log(**record)
            except Empty:
                break
            except Exception:
                pass

    def close(self):
        """핸들러를 종료합니다."""
        if self._loop and self._started:
            asyncio.run_coroutine_threadsafe(self.stop(), self._loop)
        super().close()


def setup_database_logging(level: int = logging.INFO) -> DatabaseLogHandler:
    """데이터베이스 로깅을 설정합니다.

    Args:
        level: 최소 로그 레벨

    Returns:
        DatabaseLogHandler: 설정된 핸들러

    Examples:
        >>> handler = setup_database_logging(logging.WARNING)
        >>> await handler.start()  # 서버 시작 시 호출
        >>> # ... 애플리케이션 실행 ...
        >>> await handler.stop()  # 서버 종료 시 호출
    """
    handler = DatabaseLogHandler(level=level)

    # 루트 로거에 핸들러 추가
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    return handler
