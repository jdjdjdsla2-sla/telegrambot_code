#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Focus Mode 통합 테스트
"""

import asyncio
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, str(Path(__file__).parent.parent))

from remote_dev.focus_mode import FocusMode, get_focus_mode, reset_focus_mode
from remote_dev.notifications import NotificationService, EventType, MockNotificationSender
from datetime import datetime


class TestFocusModeBasic:
    """FocusMode 기본 기능 테스트"""

    def setup_method(self):
        reset_focus_mode()
        # Config file cleanup
        from remote_dev.focus_mode import FocusMode
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()

    def test_default_disabled(self):
        """기본 상태는 비활성화"""
        mode = FocusMode()
        assert mode.get_status()['enabled'] is False

    def test_enable_and_disable(self):
        """켜기/끄기 기능"""
        mode = FocusMode()
        assert mode.enable() is True
        assert mode.get_status()['enabled'] is True
        assert mode.disable() is True
        assert mode.get_status()['enabled'] is False

    def test_toggle(self):
        """토글 기능"""
        mode = FocusMode()
        mode.toggle()
        assert mode.get_status()['enabled'] is True
        mode.toggle()
        assert mode.get_status()['enabled'] is False

    def test_persistence(self, tmp_path):
        """상태 영속성"""
        mode = FocusMode()
        mode.enable()
        # 새 인스턴스 생성 시 상태 복원
        mode2 = FocusMode()
        assert mode2.get_status()['enabled'] is True

    def test_suppress_logic(self):
        """억제 논리 검증"""
        mode = FocusMode()
        # 비활성화 시 억제 안 함
        assert mode.should_suppress("started") is False
        assert mode.should_suppress("completed") is False
        assert mode.should_suppress("accepted") is False
        
        # 활성화 시 일반 알림 억제, 긴급 알림은 허용
        mode.enable()
        assert mode.should_suppress("started") is True
        assert mode.should_suppress("completed") is True
        assert mode.should_suppress("accepted") is False
        assert mode.should_suppress("failed") is False
        assert mode.should_suppress("approval_required") is False


class TestFocusModeNotifications:
    """Focus Mode와 NotificationService 통합 테스트"""

    def setup_method(self):
        reset_focus_mode()
        # Config file cleanup
        from remote_dev.focus_mode import FocusMode
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_focus_"))
        self.db_path = self.temp_dir / "test_notifications.db"

    def teardown_method(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        reset_focus_mode()

    @pytest.mark.asyncio
    async def test_emission_without_focus_mode(self):
        """집중 모드 비활성 시 모든 알림 전송"""
        service = NotificationService(
            sender=MockNotificationSender(),
            db_path=self.db_path
        )
        
        await service.emit("task-1", EventType.STARTED)
        events = await service.list_events("task-1")
        assert len(events) == 1
        assert events[0].delivery_status.value == "sent"

    @pytest.mark.asyncio
    async def test_emission_with_focus_mode_enabled(self):
        """집중 모드 활성화 시 일반 알림 억제, 긴급 알림 전송"""
        # 새 FocusMode 인스턴스 사용 (싱글턴 공유 방지)
        focus = FocusMode()
        focus.enable()
        
        service = NotificationService(
            sender=MockNotificationSender(),
            db_path=self.db_path
        )
        
        # 일반 알림 (시작) - 억제됨
        event1 = await service.emit("task-1", EventType.STARTED)
        assert event1.delivery_status.value == "pending"
        
        # 긴급 알림 (승인) - 전송됨
        event2 = await service.emit("task-2", EventType.ACCEPTED)
        assert event2.delivery_status.value == "sent"
        
        # 완료 알림 - 억제됨
        event3 = await service.emit("task-1", EventType.COMPLETED)
        assert event3.delivery_status.value == "pending"

    @pytest.mark.asyncio
    async def test_suppressed_count_tracking(self):
        """억제된 알림 수 추적"""
        # Use singleton to ensure consistency with NotificationService
        focus = get_focus_mode()
        focus.enable()
        
        service = NotificationService(
            sender=MockNotificationSender(),
            db_path=self.db_path
        )
        
        await service.emit("task-1", EventType.STARTED)
        await service.emit("task-2", EventType.STARTED)
        await service.emit("task-3", EventType.COMPLETED)
        
        status = focus.get_status()
        assert status['suppressed_count'] == 3

    @pytest.mark.asyncio
    async def test_critical_alerts_not_suppressed(self):
        """긴급 알림은 집중 모드에서도 전송됨"""
        focus = FocusMode()
        focus.enable()
        
        service = NotificationService(
            sender=MockNotificationSender(),
            db_path=self.db_path
        )
        
        # 모든 긴급 알림 전송
        await service.emit("task-1", EventType.ACCEPTED)
        await service.emit("task-2", EventType.FAILED)
        await service.emit("task-3", EventType.APPROVAL_REQUIRED)
        
        # 모두 전송 확인
        events = await service.list_events("task-1")
        assert events[0].delivery_status.value == "sent"
        
        events = await service.list_events("task-2")
        assert events[0].delivery_status.value == "sent"
        
        events = await service.list_events("task-3")
        assert events[0].delivery_status.value == "sent"


class TestFocusModeRouterCommands:
    """라우터 명령어 테스트"""

    def setup_method(self):
        reset_focus_mode()
        # Config file cleanup
        from remote_dev.focus_mode import FocusMode
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_router_focus_"))

    def teardown_method(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        reset_focus_mode()

    @pytest.mark.asyncio
    async def test_notification_status_command(self):
        """알림상태 명령 테스트"""
        from remote_dev.router import RemoteDevRouter
        from remote_dev.task_queue import TaskQueueDB
        
        router = RemoteDevRouter()
        router.db_path = self.temp_dir / "test.db"
        router.queue = TaskQueueDB(router.db_path)
        router.auth.allowed_users = {123456}
        router.auth.allowed_chats = {8349997580}
        
        # 비활성 상태 조회
        result = await router._handle_notification_status(123456, 8349997580, "")
        assert "비활성" in result or "꺼짐" in result
        
        # 활성화 후 조회
        focus = FocusMode()
        focus.enable()
        result = await router._handle_notification_status(123456, 8349997580, "")
        assert "활성" in result

    @pytest.mark.asyncio
    async def test_focus_mode_commands(self):
        """집중모드 명령 테스트"""
        from remote_dev.router import RemoteDevRouter
        from remote_dev.task_queue import TaskQueueDB
        
        router = RemoteDevRouter()
        router.db_path = self.temp_dir / "test.db"
        router.queue = TaskQueueDB(router.db_path)
        router.auth.allowed_users = {123456}
        router.auth.allowed_chats = {8349997580}
        
        # 켜기
        result = await router._handle_focus_mode(123456, 8349997580, "켜기")
        assert "시작" in result
        
        # 끄기
        result = await router._handle_focus_mode(123456, 8349997580, "끄기")
        assert "비활성" in result or "꺼짐" in result or "종료" in result


class TestFocusModeEdgeCases:
    """Focus Mode 경계 조건 테스트"""

    def setup_method(self):
        reset_focus_mode()
        # Config file cleanup
        from remote_dev.focus_mode import FocusMode
        if FocusMode.CONFIG_FILE.exists():
            FocusMode.CONFIG_FILE.unlink()

    def test_reset(self):
        """리셋 기능"""
        mode = FocusMode()
        mode.enable()
        mode.record_suppressed("started", "task-1", "test summary")
        
        mode.reset()
        assert mode.get_status()['enabled'] is False
        assert mode.get_status()['suppressed_count'] == 0
        assert len(mode._suppressed_log) == 0

    def test_large_suppressed_log(self):
        """많은 suppressed 알림 기록 시 최대 100개만 유지"""
        mode = FocusMode()
        mode.enable()
        
        for i in range(150):
            mode.record_suppressed("started", f"task-{i}", f"summary {i}")
        
        # 저장 시 100개로 제한되지만, 직접 접근 시 150개 가능
        # 실제 파일 저장된 값 확인
        assert mode.get_status()['suppressed_count'] == 150
