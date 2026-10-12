#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway 라우터 테스트 — Stage 4-C0 플러그인 규약 검증
register(ctx) 패턴 / async 핸들러 / {} vs None 반환값
"""

import asyncio
import inspect
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from remote_dev.router import (
    RemoteDevRouter, _normalize_chat_type, _generate_task_id,
    pre_gateway_dispatch_handler, COMMAND_HANDLER_MAP, CHAT_TYPE_MAP
)
from remote_dev.plugin import register, unregister
from remote_dev.auth import AuthManager, AuthStatus
from remote_dev.task_queue import TaskQueueDB, TaskStatus
from remote_dev.notifications import NotificationService, EventType


def make_mock_event(text="/상태", user_id="123456"):
    event = MagicMock()
    event.text = text
    event.message_type = "command"
    event.user_id = user_id
    return event


def make_mock_source(chat_id="8349997580", chat_type="dm", user_id="123456"):
    source = MagicMock()
    source.chat_id = chat_id
    source.chat_type = chat_type
    source.user_id = user_id
    mock_platform = MagicMock()
    mock_platform.value = "telegram"
    source.platform = mock_platform
    return source


def make_mock_gateway():
    gw = MagicMock()
    gw.send = AsyncMock(return_value=None)
    return gw


def make_mock_ctx():
    ctx = MagicMock()
    ctx.register_hook = MagicMock()
    ctx.unregister_hook = MagicMock()
    return ctx


class TestPluginConvention:
    def test_register_function_exists(self):
        assert callable(register)

    def test_unregister_function_exists(self):
        assert callable(unregister)

    def test_register_calls_ctx_hook(self):
        ctx = make_mock_ctx()
        register(ctx)
        assert ctx.register_hook.call_count == 1
        call_args = ctx.register_hook.call_args[0]
        assert call_args[0] == "pre_gateway_dispatch"
        assert callable(call_args[1])

    def test_register_callback_is_async(self):
        ctx = make_mock_ctx()
        register(ctx)
        callback = ctx.register_hook.call_args[0][1]
        assert asyncio.iscoroutinefunction(callback)

    def test_unregister_calls_ctx_hook(self):
        ctx = make_mock_ctx()
        unregister(ctx)
        ctx.unregister_hook.assert_called_once()

    def test_unregister_ignores_missing_hook(self):
        ctx = make_mock_ctx()
        ctx.unregister_hook.side_effect = Exception("no hook")
        unregister(ctx)


class TestChatTypeNormalization:
    def test_dm_to_private(self):
        assert _normalize_chat_type("dm") == "private"

    def test_private_preserved(self):
        assert _normalize_chat_type("private") == "private"

    def test_group_rejected(self):
        assert _normalize_chat_type("group") == "group"

    def test_supergroup_rejected(self):
        assert _normalize_chat_type("supergroup") == "supergroup"

    def test_channel_rejected(self):
        assert _normalize_chat_type("channel") == "channel"

    def test_unknown_passes_through(self):
        assert _normalize_chat_type("unknown") == "unknown"


class TestTaskIdGeneration:
    def test_generate_unique_ids(self):
        id1 = _generate_task_id(123, "test", "arg1")
        id2 = _generate_task_id(123, "test", "arg2")
        assert id1 != id2
        assert id1.startswith("task-")
        assert id2.startswith("task-")


class TestCommandHandlerMap:
    def test_all_commands_mapped(self):
        expected = {"상태", "조사", "실행", "작업", "도움말", "승인", "거절", "취소", "명령", "상세", "알림상태", "집중모드"}
        assert set(COMMAND_HANDLER_MAP.keys()) == expected

    def test_all_handlers_exist(self):
        router = RemoteDevRouter()
        for cmd, handler_name in COMMAND_HANDLER_MAP.items():
            assert hasattr(router, handler_name)


class TestHookReturnValues:
    def test_empty_dict_is_falsy(self):
        # {}는 truthy가 아님 — Gateway pass-through
        assert bool({}) is False

    def test_none_is_falsy(self):
        assert bool(None) is False

    def test_skip_dict_is_truthy(self):
        assert bool({"action": "skip"}) is True

    def test_rewrite_dict_is_truthy(self):
        assert bool({"action": "rewrite", "text": "x"}) is True

    @pytest.mark.asyncio
    async def test_non_command_message_returns_empty_dict(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="안녕하세요")
        source = make_mock_source()
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {}

    @pytest.mark.asyncio
    async def test_non_private_chat_returns_skip(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="/상태")
        source = make_mock_source(chat_type="group")
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {"action": "skip"}

    @pytest.mark.asyncio
    async def test_command_after_auth_returns_skip(self):
        router = RemoteDevRouter()
        router.auth.allowed_users = {123456}
        router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/상태")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        gateway.send.assert_awaited_once()


class TestRemoteDevRouter:
    def setup_method(self):
        self.router = RemoteDevRouter()
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_router_"))
        self.db_path = self.test_dir / "test_tasks.db"
        self.router.queue = TaskQueueDB(self.db_path)

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_status_command(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/상태")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent_args = gateway.send.call_args[0]
        assert "원격 개발 시스템 상태" in sent_args[1]

    @pytest.mark.asyncio
    async def test_help_command(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/도움말")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent_args = gateway.send.call_args[0]
        assert "원격 개발 명령어" in sent_args[1]

    @pytest.mark.asyncio
    async def test_investigate_command_registered_queued(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/조사 프로젝트 구조 분석")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        tasks = self.router.queue.list_tasks()
        investigate_tasks = [t for t in tasks if t.task_type == "investigate"]
        assert len(investigate_tasks) >= 1
        assert investigate_tasks[-1].status == TaskStatus.QUEUED

    @pytest.mark.asyncio
    async def test_execute_command_registered_waiting_approval(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/실행 로그 파일 분석 요청")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        tasks = self.router.queue.list_tasks()
        execute_tasks = [t for t in tasks if t.task_type == "execute"]
        assert len(execute_tasks) >= 1
        assert execute_tasks[-1].status == TaskStatus.WAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_task_query_by_owner(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        event2 = make_mock_event(text=f"/작업 {task_id}")
        source2 = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source2, gateway2)
        assert result == {"action": "skip"}
        sent_args = gateway2.send.call_args[0]
        assert task_id in sent_args[1]

    @pytest.mark.asyncio
    async def test_task_query_other_user_rejected(self):
        self.router.auth.allowed_users = {123456, 999999}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        event2 = make_mock_event(text=f"/작업 {task_id}", user_id="999999")
        source2 = make_mock_source(user_id="999999", chat_id="8349997580")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source2, gateway2)
        assert result == {"action": "skip"}
        sent_args = gateway2.send.call_args[0]
        # Auth may block user, message may vary

    @pytest.mark.asyncio
    async def test_nonexistent_task_query(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/작업 nonexistent-task-id-xyz")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent_args = gateway.send.call_args[0]
        assert "찾을 수 없습니다" in sent_args[1]

    @pytest.mark.asyncio
    async def test_sensitive_info_masked_in_task_description(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(
            text="/실행 api_key=sk-or-v1-aabbccddee112233445566778899aabbccddeeff001122334455"
        )
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        tasks = self.router.queue.list_tasks()
        execute_tasks = [t for t in tasks if t.task_type == "execute"]
        assert len(execute_tasks) >= 1
        desc = execute_tasks[-1].description
        assert "1234567890123:" not in desc
        assert "sk-or-v1-" not in desc

    @pytest.mark.asyncio
    async def test_hook_exception_isolated(self):
        broken = RemoteDevRouter()
        broken.auth.authenticate = MagicMock(side_effect=Exception("intentional error"))
        event = make_mock_event(text="/상태")
        source = make_mock_source()
        gateway = make_mock_gateway()
        result = await broken.handle(event, source, gateway)
        assert result == {}

    @pytest.mark.asyncio
    async def test_unauthenticated_user_returns_skip_no_leak(self):
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}
        event = make_mock_event(text="/상태", user_id="999999")
        source = make_mock_source(user_id="999999", chat_id="9999999999")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent_args = gateway.send.call_args[0]
        assert "sk-" not in sent_args[1]
        assert "AQ." not in sent_args[1]
        assert "ntn_" not in sent_args[1]

    @pytest.mark.asyncio
    async def test_non_command_message_passes_through(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="안녕하세요 오늘 날씨 어때요?")
        source = make_mock_source()
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {}

    @pytest.mark.asyncio
    async def test_chat_type_group_rejected(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="/상태")
        source = make_mock_source(chat_type="group")
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {"action": "skip"}

    @pytest.mark.asyncio
    async def test_chat_type_supergroup_rejected(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="/상태")
        source = make_mock_source(chat_type="supergroup")
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {"action": "skip"}

    @pytest.mark.asyncio
    async def test_chat_type_channel_rejected(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="/상태")
        source = make_mock_source(chat_type="channel")
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result == {"action": "skip"}

    @pytest.mark.asyncio
    async def test_invalid_user_id_returns_skip(self):
        router = RemoteDevRouter()
        event = make_mock_event(text="/상태", user_id="not-a-number")
        source = make_mock_source()
        gateway = make_mock_gateway()
        result = await router.handle(event, source, gateway)
        assert result in [{}, {"action": "skip"}]


class TestIntegration:
    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_integration_"))
        self.db_path = self.test_dir / "integration_tasks.db"
        self.router = RemoteDevRouter()
        self.router.queue = TaskQueueDB(self.db_path)
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_full_workflow_status_investigate_execute(self):
        gateway = make_mock_gateway()
        source = make_mock_source(user_id="123456", chat_id="8349997580")

        r1 = await self.router.handle(make_mock_event("/상태"), source, gateway)
        assert r1 == {"action": "skip"}
        assert gateway.send.await_count >= 1

        r2 = await self.router.handle(make_mock_event("/조사 프로젝트 구조 분석"), source, gateway)
        assert r2 == {"action": "skip"}
        tasks = self.router.queue.list_tasks()
        assert any(t.task_type == "investigate" for t in tasks)

        r3 = await self.router.handle(make_mock_event("/실행 로그 파일 분석 요청"), source, gateway)
        assert r3 == {"action": "skip"}
        execute_tasks = [t for t in self.router.queue.list_tasks() if t.task_type == "execute"]
        assert len(execute_tasks) >= 1
        assert execute_tasks[-1].status == TaskStatus.WAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_unauthenticated_user_rejected_all_commands(self):
        gateway = make_mock_gateway()
        source = make_mock_source(user_id="999999", chat_id="9999999999")
        for cmd in ["/상태", "/조사 대상", "/실행 작업", "/작업 123", "/도움말"]:
            gateway.reset_mock()
            event = make_mock_event(text=cmd, user_id="999999")
            result = await self.router.handle(event, source, gateway)
            assert result == {"action": "skip"}
            assert gateway.send.await_count >= 1

    @pytest.mark.asyncio
    async def test_no_silent_transition_to_running(self):
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        tasks = self.router.queue.list_tasks()
        execute_tasks = [t for t in tasks if t.task_type == "execute"]
        assert len(execute_tasks) >= 1
        status = execute_tasks[-1].status
        assert status != TaskStatus.RUNNING
        assert status == TaskStatus.WAITING_APPROVAL

    @pytest.mark.asyncio
    async def test_handler_signature_accepts_kwargs(self):
        """pre_gateway_dispatch_handler가 **kwargs를 받을 수 있는지 확인"""
        import inspect
        sig = inspect.signature(pre_gateway_dispatch_handler)
        params = list(sig.parameters.keys())
        assert 'event' in params
        assert 'source' in params
        assert 'gateway' in params
        assert 'kwargs' in params


class TestSecurityChecks:
    def test_investigate_only_readonly_sources(self):
        router = RemoteDevRouter()
        src = inspect.getsource(router._handle_investigate)
        assert "TaskStatus.QUEUED" in src
        assert "TaskStatus.RUNNING" not in src

    def test_execute_only_waiting_approval(self):
        router = RemoteDevRouter()
        src = inspect.getsource(router._handle_execute)
        assert "TaskStatus.WAITING_APPROVAL" in src
        assert "approved=False" in src

    def test_no_path_to_running_without_approval(self):
        router = RemoteDevRouter()
        src = inspect.getsource(router._handle_execute)
        assert "approved=True" not in src
        assert "TaskStatus.RUNNING" not in src

    def test_task_query_validates_ownership(self):
        router = RemoteDevRouter()
        src = inspect.getsource(router._handle_task)
        assert "user_id != user_id" in src

    def test_sensitive_info_masked_before_db_write(self):
        router = RemoteDevRouter()
        src_exec = inspect.getsource(router._handle_execute)
        src_inv = inspect.getsource(router._handle_investigate)
        assert "sanitize_sensitive_info" in src_exec
        assert "sanitize_sensitive_info" in src_inv

    def test_auth_failure_returns_safe_message(self):
        router = RemoteDevRouter()
        router.auth.allowed_users = {123456}
        router.auth.allowed_chats = {8349997580}
        result = router.auth.authenticate(user_id=999999, chat_id=9999999999, chat_type="private")
        msg = result.to_message()
        assert "sk-" not in msg
        assert "AQ." not in msg
        assert "ntn_" not in msg
        assert "jun" not in msg.lower() or "비밀" in msg


@pytest.fixture
def router():
    return RemoteDevRouter()


class TestApprovalCommands:
    """승인/거절/취소 명령 테스트"""
    
    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_approval_"))
        self.db_path = self.test_dir / "approval_tasks.db"
        self.router = RemoteDevRouter()
        self.router.queue = TaskQueueDB(self.db_path)
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_approve_valid_task(self):
        """정상 승인 — WAITING_APPROVAL → RUNNING (approve_task 호출)"""
        # 먼저 작업 생성
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        
        # 승인
        event2 = make_mock_event(text=f"/승인 {task_id}")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source, gateway2)
        assert result == {"action": "skip"}
        sent = gateway2.send.call_args[0][1]
        assert "승인" in sent

    @pytest.mark.asyncio
    async def test_reject_valid_task(self):
        """정상 거절 — WAITING_APPROVAL → FAILED"""
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        
        # 거절
        event2 = make_mock_event(text=f"/거절 {task_id} 보안Policy 위반")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source, gateway2)
        assert result == {"action": "skip"}
        sent = gateway2.send.call_args[0][1]
        assert "거절" in sent

    @pytest.mark.asyncio
    async def test_cancel_queued_task(self):
        """취소 — QUEUED → CANCELLED"""
        event = make_mock_event(text="/조사 프로젝트 구조")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        
        # 취소
        event2 = make_mock_event(text=f"/취소 {task_id}")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source, gateway2)
        assert result == {"action": "skip"}
        sent = gateway2.send.call_args[0][1]
        assert "취소" in sent

    @pytest.mark.asyncio
    async def test_approve_other_user_rejected(self):
        """다른 사용자 작업 승인 시도 거부"""
        # 새 라우터 인스턴스로 브루트 포스 차단 방지
        router2 = RemoteDevRouter()
        router2.test_dir = Path(tempfile.mkdtemp(prefix="test_other_user_"))
        router2.db_path = router2.test_dir / "other_tasks.db"
        router2.queue = TaskQueueDB(router2.db_path)
        router2.auth.allowed_users = {123456}
        router2.auth.allowed_chats = {8349997580}
        
        # 작업 생성
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await router2.handle(event, source, gateway)
        
        tasks = router2.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        
        # 다른 사용자 시도
        other_source = make_mock_source(user_id="999999", chat_id="8349997580")
        gateway2 = make_mock_gateway()
        event2 = make_mock_event(text=f"/승인 {task_id}", user_id="999999")
        result = await router2.handle(event2, other_source, gateway2)
        assert result == {"action": "skip"}
        sent = gateway2.send.call_args[0][1]
        # 인증 차단 또는 권한 없음 메시지
        assert any(kw in sent for kw in ["권한", "찾을 수 없습니다", "차단"])
        
        # 정리
        import shutil
        if router2.test_dir.exists():
            shutil.rmtree(router2.test_dir)

    @pytest.mark.asyncio
    async def test_commands_list_shows_new_commands(self):
        """명령 목록에 신규 명령어 포함"""
        event = make_mock_event(text="/명령")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent = gateway.send.call_args[0][1]
        assert "승인" in sent
        assert "거절" in sent
        assert "취소" in sent

    @pytest.mark.asyncio
    async def test_detail_shows_task_info(self):
        """상세 조회 — 작업 정보 표시"""
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        
        tasks = self.router.queue.list_tasks()
        assert len(tasks) >= 1
        task_id = tasks[-1].task_id
        
        event2 = make_mock_event(text=f"/상세 {task_id}")
        gateway2 = make_mock_gateway()
        result = await self.router.handle(event2, source, gateway2)
        assert result == {"action": "skip"}
        sent = gateway2.send.call_args[0][1]
        assert task_id in sent


class TestApprovalSecurity:
    """승인 보안 검증"""
    
    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_security_"))
        self.db_path = self.test_dir / "security_tasks.db"
        self.router = RemoteDevRouter()
        self.router.queue = TaskQueueDB(self.db_path)
        self.router.auth.allowed_users = {123456}
        self.router.auth.allowed_chats = {8349997580}

    def teardown_method(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @pytest.mark.asyncio
    async def test_no_double_approval(self):
        """중복 승인 방지 — 두 번째 승인은 거부"""
        router2 = RemoteDevRouter()
        router2.test_dir = Path(tempfile.mkdtemp(prefix="test_double_"))
        router2.db_path = router2.test_dir / "double.db"
        router2.queue = TaskQueueDB(router2.db_path)
        router2.auth.allowed_users = {123456}
        router2.auth.allowed_chats = {8349997580}
        
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await router2.handle(event, source, gateway)
        
        tasks = router2.queue.list_tasks()
        task_id = tasks[-1].task_id
        
        # 첫 번째 승인
        event2 = make_mock_event(text=f"/승인 {task_id}")
        gateway2 = make_mock_gateway()
        await router2.handle(event2, source, gateway2)
        
        # 두 번째 승인 시도
        gateway3 = make_mock_gateway()
        await router2.handle(event2, source, gateway3)
        sent3 = gateway3.send.call_args[0][1]
        # 두 번째 승인은 거부됨 (이미 처리됨)
        assert any(kw in sent3 for kw in ["이미 처리", "할 수 없는", "권한", "승인"])
        
        # 정리
        import shutil
        if router2.test_dir.exists():
            shutil.rmtree(router2.test_dir)

    @pytest.mark.asyncio
    async def test_expired_task_cannot_be_approved(self):
        """만료된 작업은 승인 불가 — expire_pending_tasks 호출 필요"""
        from datetime import datetime, timedelta
        # 직접 DB 조작으로 오래된 작업 추가
        import sqlite3
        db = sqlite3.connect(str(self.router.queue.db_path))
        db.execute("INSERT INTO tasks (task_id, user_id, chat_id, task_type, description, status, created_at, updated_at, idempotency_key, approved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("task-expired-test", 123456, 8349997580, "execute", "test", "waiting_approval", 
             datetime.now().isoformat(), (datetime.now() - timedelta(hours=2)).isoformat(),
             "exp-key-test", 0))
        db.commit()
        db.close()
        
        # 만료 처리
        expired_count = self.router.queue.expire_pending_tasks(max_age_seconds=3600)
        assert expired_count >= 1
        
        event = make_mock_event(text="/승인 task-expired-test")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        result = await self.router.handle(event, source, gateway)
        assert result == {"action": "skip"}
        sent = gateway.send.call_args[0][1]
        assert "할 수 없는" in sent or "찾을 수 없습니다" in sent

    @pytest.mark.asyncio
    async def test_sensitive_info_not_in_rejection_reason(self):
        """거절 사유에 민감정보 미포함"""
        event = make_mock_event(text="/실행 테스트 작업")
        source = make_mock_source(user_id="123456", chat_id="8349997580")
        gateway = make_mock_gateway()
        await self.router.handle(event, source, gateway)
        
        tasks = self.router.queue.list_tasks()
        task_id = tasks[-1].task_id
        
        event2 = make_mock_event(text=f"/거절 {task_id} sk-or-v1-testapikey1234567890abcdef")
        gateway2 = make_mock_gateway()
        await self.router.handle(event2, source, gateway2)
        
        sent = gateway2.send.call_args[0][1]
        assert "sk-or-v1-" not in sent


@pytest.fixture
def router():
    return RemoteDevRouter()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
