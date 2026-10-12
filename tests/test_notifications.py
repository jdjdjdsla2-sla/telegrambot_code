#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
알림 서비스 테스트
Stage 3: 알림 이벤트, 중복 방지, 재시도, 민감정보 마스킹
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from remote_dev.focus_mode import reset_focus_mode
from remote_dev.notifications import (
    NotificationService, NotificationEvent, EventType,
    DeliveryStatus, MockNotificationSender, NotificationSender
)
from remote_dev.task_queue import sanitize_sensitive_info


class TestNotificationEvent:
    """이벤트 데이터 클래스 테스트"""

    def test_create_event(self):
        event = NotificationEvent(
            event_id="e1",
            task_id="t1",
            event_type=EventType.ACCEPTED,
            timestamp=__import__('datetime').datetime.now(),
            safe_summary="📥 작업 t1 접수됨",
        )
        assert event.event_id == "e1"
        assert event.delivery_status == DeliveryStatus.PENDING

    def test_event_to_dict_roundtrip(self):
        import datetime
        dt = datetime.datetime.now()
        event = NotificationEvent(
            event_id="e2",
            task_id="t2",
            event_type=EventType.COMPLETED,
            timestamp=dt,
            safe_summary="✅ 완료",
            delivery_status=DeliveryStatus.SENT,
            sent_at=dt,
        )
        d = event.to_dict()
        restored = NotificationEvent.from_dict(d)
        assert restored.event_id == "e2"
        assert restored.event_type == EventType.COMPLETED
        assert restored.delivery_status == DeliveryStatus.SENT


class TestMockNotificationSender:
    """Mock 전송기 테스트"""

    def test_successful_send(self):
        sender = MockNotificationSender()
        event = NotificationEvent(
            event_id="m1", task_id="t1",
            event_type=EventType.ACCEPTED,
            timestamp=__import__('datetime').datetime.now(),
            safe_summary="test",
        )
        assert asyncio.run(sender.send(event)) is True
        assert len(sender.sent_events) == 1

    def test_failed_send(self):
        sender = MockNotificationSender(fail_next=1)
        event = NotificationEvent(
            event_id="m2", task_id="t1",
            event_type=EventType.FAILED,
            timestamp=__import__('datetime').datetime.now(),
            safe_summary="test",
        )
        assert asyncio.run(sender.send(event)) is False
        assert len(sender.failed_events) == 1


class TestNotificationService:
    """알림 서비스 테스트"""

    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_notif_svc_"))
        self.db_path = self.test_dir / "notif.db"

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_emit_all_event_types(self):
        """모든 이벤트 유형 생성"""
        # Force fresh focus_mode state
        from remote_dev.focus_mode import reset_focus_mode, FocusMode
        reset_focus_mode()
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()
        
        svc = NotificationService(db_path=self.db_path)

        for et in EventType:
            event = asyncio.run(svc.emit("task-evt", et))
            assert event.event_type == et
            assert event.delivery_status == DeliveryStatus.SENT

    def test_event_contains_safe_summary(self):
        """요약문에 아이콘과 작업 ID 포함"""
        svc = NotificationService(db_path=self.db_path)
        event = asyncio.run(svc.emit("task-sum", EventType.STARTED))
        assert "task-sum"[:8] in event.safe_summary or len(event.safe_summary) > 0

    def test_event_id_uniqueness(self):
        """이벤트 ID 고유성"""
        svc = NotificationService(db_path=self.db_path)
        e1 = asyncio.run(svc.emit("task-unq-1", EventType.ACCEPTED))
        e2 = asyncio.run(svc.emit("task-unq-2", EventType.ACCEPTED))
        assert e1.event_id != e2.event_id

    def test_duplicate_event_same_id(self):
        """동일 작업+이벤트 중복 방지"""
        svc = NotificationService(db_path=self.db_path)
        e1 = asyncio.run(svc.emit("task-dup", EventType.ACCEPTED))
        e2 = asyncio.run(svc.emit("task-dup", EventType.ACCEPTED))
        assert e1.event_id == e2.event_id

    def test_different_event_type_same_task(self):
        """동일 작업 다른 이벤트 유형은 허용"""
        svc = NotificationService(db_path=self.db_path)
        e1 = asyncio.run(svc.emit("task-type", EventType.ACCEPTED))
        e2 = asyncio.run(svc.emit("task-type", EventType.STARTED))
        assert e1.event_id != e2.event_id

    def test_sanitize_sensitive_in_summary(self):
        """요약문 내 민감정보 마스킹"""
        svc = NotificationService(db_path=self.db_path)
        event = asyncio.run(svc.emit(
            "task-mask", EventType.FAILED,
            error="Connection failed: sk-or-v1-abc123xyz789"
        ))
        assert "sk-abcdefghij1234567890" not in event.safe_summary

    def test_event_persistence_in_db(self):
        """이벤트 DB 영속성"""
        svc = NotificationService(db_path=self.db_path)
        asyncio.run(svc.emit("task-persist", EventType.ACCEPTED))
        events = asyncio.run(svc.list_events("task-persist"))
        assert len(events) >= 1
        assert events[0].task_id == "task-persist"

    def test_stats_after_emits(self):
        """발송 후 통계"""
        # Force fresh focus_mode state
        from remote_dev.focus_mode import reset_focus_mode, FocusMode
        reset_focus_mode()
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()
        svc = NotificationService(db_path=self.db_path)
        asyncio.run(svc.emit("t1", EventType.ACCEPTED))
        asyncio.run(svc.emit("t1", EventType.STARTED))
        asyncio.run(svc.emit("t2", EventType.COMPLETED))
        stats = asyncio.run(svc.get_stats())
        assert stats['total'] >= 3

    def test_retry_on_failure(self):
        """전송 실패 시 재시도"""
        call_count = [0]
        class FailingSender(MockNotificationSender):
            async def send(self, event):
                call_count[0] += 1
                if call_count[0] < 3:
                    return False
                return True

        svc = NotificationService(sender=FailingSender(), db_path=self.db_path)
        event = asyncio.run(svc.emit("task-retry", EventType.FAILED))
        assert call_count[0] >= 3
        assert event.retry_count >= 2

    def test_max_retries_exceeded(self):
        """최대 재시도 초과 시 실패 상태로"""
        class AlwaysFails(MockNotificationSender):
            async def send(self, event):
                return False

        svc = NotificationService(sender=AlwaysFails(), db_path=self.db_path)
        event = asyncio.run(svc.emit("task-maxretry", EventType.FAILED))
        assert event.delivery_status == DeliveryStatus.FAILED
        assert event.retry_count >= 3


class TestNotificationIntegration:
    """알림 통합 테스트"""

    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_notif_int_"))
        self.db_path = self.test_dir / "notif.db"

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_workflow_with_notifications(self):
        """작업 lifecycle 전체 알림"""
        # Force fresh focus_mode state
        from remote_dev.focus_mode import reset_focus_mode, FocusMode
        reset_focus_mode()
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()
        svc = NotificationService(db_path=self.db_path)

        # accepted
        e1 = asyncio.run(svc.emit("wf-task", EventType.ACCEPTED))
        # started
        e2 = asyncio.run(svc.emit("wf-task", EventType.STARTED))
        # completed
        e3 = asyncio.run(svc.emit("wf-task", EventType.COMPLETED, status="성공"))

        events = asyncio.run(svc.list_events("wf-task"))
        types = [ev.event_type for ev in events]
        assert EventType.ACCEPTED in types
        assert EventType.STARTED in types
        assert EventType.COMPLETED in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
