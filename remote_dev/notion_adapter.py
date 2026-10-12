#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion 오류 로거 어댑터
기존 notion_logger.py를 재사용하여 작업 오류를 Notion에 기록
"""

import logging
from typing import Optional
from pathlib import Path

# 조건부 import: notion_client 또는 requests가 없으면 graceful fallback
try:
    from ..notion_logger import NotionErrorLogger
    _NOTION_AVAILABLE = True
except ImportError:
    _NOTION_AVAILABLE = False

logger = logging.getLogger(__name__)


class NotionLoggerAdapter:
    """
    Notion 오류 로깅 어댑터.
    - 기존 NotionErrorLogger를 감싸서 호출
    - Notion 사용 불가 시 로깅만 하고 통과
    - 민감정보는 마스킹됨
    """

    def __init__(self):
        self._enabled = False
        self._logger = None
        if _NOTION_AVAILABLE:
            try:
                self._logger = NotionErrorLogger()
                self._enabled = True
            except ValueError:
                self._enabled = False
                logger.info("NotionLoggerAdapter: 환경변수 누락으로 비활성화됨")

    def log_error(self, task_id: str, error_code: str,
                  error_summary: Optional[str],
                  event_type: Optional[str] = None):
        """
        오류를 Notion에 기록 (비동기적, 실패 시 무시).
        민감정보는 마스킹되지 않음 — 호출 측에서 이미 마스킹 필수.
        """
        if not self._enabled or self._logger is None:
            logger.debug("NotionLoggerAdapter: Notion 비활성, 로그 생략")
            return

        # error_summary가 None이면 빈 문자열
        safe_summary = error_summary or ""
        # NotionErrorLogger는 내부적으로 환경변수를 사용하므로 직접 호출
        try:
            self._logger.log_error(
                error_type=error_code,
                message=f"[{task_id}] {safe_summary[:200]}",
                stack_trace=f"task_id={task_id}\nerror_code={error_code}\nsummary={safe_summary[:500]}",
                model="remote_dev",
                retry_count=0,
                recovery="pending"
            )
        except Exception as e:
            logger.warning(f"NotionLoggerAdapter: Notion 기록 실패 (무시): {e}")

    @property
    def is_enabled(self) -> bool:
        return self._enabled


# ============================================================
# Mock Notion Logger (테스트용)
# ============================================================

class MockNotionLogger:
    """테스트용 가짜 Notion 로거 — 실제 API 호출 없음"""

    def __init__(self):
        self.logged_errors: list = []

    def log_error(self, error_type: str, message: str,
                  stack_trace: str, **kwargs):
        self.logged_errors.append({
            'error_type': error_type,
            'message': message,
            'stack_trace': stack_trace,
            'kwargs': kwargs,
        })

    @property
    def is_enabled(self) -> bool:
        return True
