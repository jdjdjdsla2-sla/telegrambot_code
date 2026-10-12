#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
알림 모듈
작업 이벤트 알림 발송, 중복 방지, 재시도 정책
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite
from .task_queue import sanitize_sensitive_info
from .focus_mode import get_focus_mode

logger = logging.getLogger(__name__)


# ============================================================
# 열거형
# ============================================================

class EventType(Enum):
    """알림 이벤트 유형"""
    ACCEPTED        = "accepted"
    STARTED         = "started"
    COMPLETED       = "completed"
    FAILED          = "failed"
    APPROVAL_REQUIRED = "approval_required"


class DeliveryStatus(Enum):
    """전송 상태"""
    PENDING   = "pending"
    SENT      = "sent"
    FAILED    = "failed"
    RETRYING  = "retrying"


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class NotificationEvent:
    """알림 이벤트"""
    event_id: str
    task_id: str
    event_type: EventType
    timestamp: datetime
    safe_summary: str
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    retry_count: int = 0
    last_error: Optional[str] = None
    sent_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'event_id': self.event_id,
            'task_id': self.task_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'safe_summary': sanitize_sensitive_info(self.safe_summary),
            'delivery_status': self.delivery_status.value,
            'retry_count': self.retry_count,
            'last_error': self.last_error,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NotificationEvent':
        return cls(
            event_id=data['event_id'],
            task_id=data['task_id'],
            event_type=EventType(data['event_type']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            safe_summary=data['safe_summary'],
            delivery_status=DeliveryStatus(data['delivery_status']),
            retry_count=data.get('retry_count', 0),
            last_error=data.get('last_error'),
            sent_at=datetime.fromisoformat(data['sent_at']) if data.get('sent_at') else None,
        )


# ============================================================
# 알림 전송 인터페이스
# ============================================================

class NotificationSender:
    """
    알림 전송 클래스 (추상 대신 구체 구현으로 통합).
    서브클래싱하여 커스터마이즈 가능.
    """

    # 재시도 정책 상수
    MAX_RETRIES = 3
    INITIAL_DELAY = 1.0
    BACKOFF_FACTOR = 2.0

    def __init__(self):
        self.sent_events: List[NotificationEvent] = []
        self.failed_events: List[NotificationEvent] = []

    async def send(self, event: NotificationEvent) -> bool:
        """이벤트 전송. 성공 시 True, 실패 시 False 반환."""
        raise NotImplementedError("서브클래스에서 구현 필수")

    def generate_summary(self, event_type: EventType, task_id: str,
                         status: Optional[str] = None,
                         error: Optional[str] = None) -> str:
        """사용자 표시용 안전한 요약 생성"""
        icons = {
            EventType.ACCEPTED: "📥",
            EventType.STARTED: "🚀",
            EventType.COMPLETED: "✅",
            EventType.FAILED: "❌",
            EventType.APPROVAL_REQUIRED: "⏳",
        }
        icon = icons.get(event_type, "📌")
        parts = [f"{icon} 작업 {task_id[:8]}..."]
        if status:
            parts.append(f"상태: {status}")
        if error:
            parts.append(f"오류: {sanitize_sensitive_info(error)[:100]}")
        return " | ".join(parts)


# ============================================================
# Mock 전송기 (테스트용)
# ============================================================

class MockNotificationSender(NotificationSender):
    """테스트용 가짜 전송기 — 실제 전송 없이 기록만 함"""

    def __init__(self, fail_next: int = 0):
        super().__init__()
        self._fail_next = fail_next

    async def send(self, event: NotificationEvent) -> bool:
        self.sent_events.append(event)
        if self._fail_next > 0:
            self._fail_next -= 1
            self.failed_events.append(event)
            return False
        return True


# ============================================================
# 알림 서비스
# ============================================================

class NotificationService:
    """알림 서비스: 이벤트 저장, 중복 방지, 재시도"""

    def __init__(self, sender: Optional[NotificationSender] = None,
                 db_path: Optional[Path] = None):
        self.sender = sender or MockNotificationSender()
        self.db_path = db_path or (Path.home() / ".hermes" / "remote_notifications.db")
        self._event_store: Dict[str, NotificationEvent] = {}
        self._sent_keys: set = set()
        self._lock = __import__('threading').Lock()
        self._initialized = False
        self._initialized = False

    async def initialize(self):
        """DB 초기화 (테이블 생성, 기존 데이터 보존)"""
        conn = await aiosqlite.connect(str(self.db_path))
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    event_id       TEXT PRIMARY KEY,
                    task_id        TEXT NOT NULL,
                    event_type     TEXT NOT NULL,
                    timestamp      TEXT NOT NULL,
                    safe_summary   TEXT NOT NULL,
                    delivery_status TEXT NOT NULL,
                    retry_count    INTEGER NOT NULL DEFAULT 0,
                    last_error     TEXT,
                    sent_at        TEXT
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_task ON notifications(task_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notif_status ON notifications(delivery_status)"
            )
            await conn.commit()
        finally:
            await conn.close()

    def _make_event_id(self, task_id: str, event_type: EventType) -> str:
        """중복 방지용 이벤트 ID 생성"""
        raw = f"{task_id}:{event_type.value}:{datetime.now().isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def emit(self, task_id: str, event_type: EventType,
                   status: Optional[str] = None,
                   error: Optional[str] = None) -> NotificationEvent:
        """
        알림 이벤트 발생. 중복 방지 + 재시도 포함 + 집중 모드 필터링.
        """
        if not getattr(self, '_initialized', False):
            await self.initialize()
            self._initialized = True
        
        # 집중 모드 체크: 억제 대상이면 기록만 하고 전송跳过
        focus = get_focus_mode()
        if focus.should_suppress(event_type.value):
            event_id = self._make_event_id(task_id, event_type)
            summary = self.sender.generate_summary(event_type, task_id, status, error)
            event = NotificationEvent(
                event_id=event_id,
                task_id=task_id,
                event_type=event_type,
                timestamp=datetime.now(),
                safe_summary=summary,
            )
            focus.record_suppressed(event_type.value, task_id, summary)
            logger.info("focus_mode: suppressed notification %s for task %s", event_type.value, task_id[:8])
            return event

        dup_key = f"{task_id}:{event_type.value}"
        with self._lock:
            if dup_key in self._sent_keys:
                stored = self._event_store.get(dup_key)
                if stored:
                    return stored

        event_id = self._make_event_id(task_id, event_type)
        summary = self.sender.generate_summary(event_type, task_id, status, error)
        event = NotificationEvent(
            event_id=event_id,
            task_id=task_id,
            event_type=event_type,
            timestamp=datetime.now(),
            safe_summary=summary,
        )

        success = await self._send_with_retry(event)

        if success:
            event.delivery_status = DeliveryStatus.SENT
            event.sent_at = datetime.now()
            with self._lock:
                self._sent_keys.add(dup_key)
        else:
            event.delivery_status = DeliveryStatus.FAILED

        with self._lock:
            self._event_store[dup_key] = event

        await self._save_event(event)
        return event

    async def _send_with_retry(self, event: NotificationEvent) -> bool:
        """지수 백오프 재시도"""
        for attempt in range(self.sender.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    delay = self.sender.INITIAL_DELAY * (self.sender.BACKOFF_FACTOR ** (attempt - 1))
                    await asyncio.sleep(delay)
                    event.retry_count = attempt
                    event.delivery_status = DeliveryStatus.RETRYING

                success = await self.sender.send(event)
                if success:
                    return True
            except Exception as e:
                event.last_error = sanitize_sensitive_info(str(e))
                event.retry_count = attempt

        event.delivery_status = DeliveryStatus.FAILED
        return False

    async def _save_event(self, event: NotificationEvent):
        """이벤트를 SQLite에 저장"""
        conn = await aiosqlite.connect(str(self.db_path))
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO notifications
                   (event_id, task_id, event_type, timestamp, safe_summary,
                    delivery_status, retry_count, last_error, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id, event.task_id, event.event_type.value,
                    event.timestamp.isoformat(), event.safe_summary,
                    event.delivery_status.value, event.retry_count,
                    event.last_error,
                    event.sent_at.isoformat() if event.sent_at else None,
                )
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_event(self, event_id: str) -> Optional[NotificationEvent]:
        conn = await aiosqlite.connect(str(self.db_path))
        try:
            cur = await conn.execute(
                "SELECT * FROM notifications WHERE event_id = ?", (event_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
            cols = ['event_id','task_id','event_type','timestamp','safe_summary',
                    'delivery_status','retry_count','last_error','sent_at']
            return NotificationEvent.from_dict(dict(zip(cols, row)))
        finally:
            await conn.close()

    async def list_events(self, task_id: str, limit: int = 20) -> List[NotificationEvent]:
        conn = await aiosqlite.connect(str(self.db_path))
        try:
            cur = await conn.execute(
                "SELECT * FROM notifications WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                (task_id, limit)
            )
            rows = await cur.fetchall()
            cols = ['event_id','task_id','event_type','timestamp','safe_summary',
                    'delivery_status','retry_count','last_error','sent_at']
            return [NotificationEvent.from_dict(dict(zip(cols, r))) for r in rows]
        finally:
            await conn.close()

    async def get_stats(self) -> dict:
        """알림 통계 반환"""
        conn = await aiosqlite.connect(str(self.db_path))
        try:
            cur = await conn.execute(
                "SELECT delivery_status, COUNT(*) FROM notifications GROUP BY delivery_status"
            )
            rows = await cur.fetchall()
            stats = {'total': 0}
            for status, count in rows:
                stats[status] = count
                stats['total'] += count
            return stats
        finally:
            await conn.close()

    async def close(self):
        """연결 정리"""
        pass  # aiosqlite는 각 메서드에서 연결을 닫음
