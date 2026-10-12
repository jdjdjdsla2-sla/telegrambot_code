#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gateway 라우터 모듈
pre_gateway_dispatch 훅 핸들러 — 원격 개발 명령 라우팅
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict

from .auth import AuthManager, AuthStatus
from .command_parser import CommandParser, CommandLevel
from .task_queue import TaskQueueDB, TaskInfo, TaskStatus, sanitize_sensitive_info
from .notifications import NotificationService, EventType, MockNotificationSender
from .focus_mode import get_focus_mode

logger = logging.getLogger(__name__)

# Korean command to handler method name mapping
COMMAND_HANDLER_MAP = {
    '상태': '_handle_status',
    '조사': '_handle_investigate',
    '실행': '_handle_execute',
    '작업': '_handle_task',
    '도움말': '_handle_help',
    '승인': '_handle_approve',
    '거절': '_handle_reject',
    '취소': '_handle_cancel',
    '명령': '_handle_commands',
    '상세': '_handle_detail',
    '알림상태': '_handle_notification_status',
    '집중모드': '_handle_focus_mode',
}

# chat_type 매핑: Gateway 'dm' ↔ AuthManager 'private'
CHAT_TYPE_MAP = {
    'dm': 'private',
    'private': 'private',
    'group': 'group',
    'supergroup': 'supergroup',
    'channel': 'channel',
}


def _normalize_chat_type(gateway_chat_type: str) -> str:
    """Gateway chat_type을 AuthManager 표준으로 변환"""
    return CHAT_TYPE_MAP.get(gateway_chat_type, gateway_chat_type)


def _generate_task_id(user_id: int, command: str, args: str) -> str:
    """작업 고유 ID 생성"""
    return f"task-{uuid.uuid4().hex[:8]}"


class RemoteDevRouter:
    """Gateway pre_gateway_dispatch 훅 핸들러"""

    def __init__(self):
        self.auth = AuthManager()
        self.parser = CommandParser()
        self.queue = TaskQueueDB()
        self.notifier = NotificationService(sender=MockNotificationSender())

    async def handle(self, event: Any, source: Any, gateway: Any, **kwargs) -> Dict[str, Any]:
        """
        pre_gateway_dispatch 훅 콜백.

        Returns:
            dict: {"action": "skip"} 또는 {} (정상 처리)
        """
        try:
            # 1. 명령어 감지
            text = getattr(event, 'text', '') or ''
            if not text.startswith('/'):
                return {}  # 일반 메시지는 Gateway에 위임

            # 2. chat_type 검증 및 정규화
            gateway_chat_type = getattr(source, 'chat_type', 'dm') or 'dm'
            chat_type = _normalize_chat_type(gateway_chat_type)

            if chat_type != 'private':
                logger.info("remote_dev: rejected from %s chat (user=%s)",
                           gateway_chat_type, getattr(source, 'user_id', 'unknown'))
                return {"action": "skip"}

            # 3. user_id/chat_id 추출 및 타입 변환
            try:
                user_id = int(getattr(source, 'user_id', '') or 0)
                chat_id = int(getattr(source, 'chat_id', '') or 0)
            except (ValueError, TypeError):
                return {"action": "skip"}

            if user_id <= 0 or chat_id <= 0:
                return {"action": "skip"}

            # 4. 인증
            auth_result = self.auth.authenticate(
                user_id=user_id,
                chat_id=chat_id,
                chat_type=chat_type
            )

            if auth_result.status != AuthStatus.SUCCESS:
                await self._send_reply(gateway, chat_id, auth_result.to_message())
                return {"action": "skip"}

            # 5. 명령어 파싱
            clean_text = text.strip()
            cmd_result = self.parser.parse(clean_text)

            if not cmd_result.success:
                await self._send_reply(gateway, chat_id, cmd_result.to_message())
                return {"action": "skip"}

            # 6. 명령어별 처리 - Korean command mapping to handler
            handler_name = COMMAND_HANDLER_MAP.get(cmd_result.command) if cmd_result.command else None
            handler = getattr(self, handler_name, None) if handler_name else None
            if handler:
                reply = await handler(user_id, chat_id, cmd_result.args or '')
            else:
                reply = await self._handle_unknown(user_id, chat_id, cmd_result.command or "unknown")

            await self._send_reply(gateway, chat_id, reply)
            return {"action": "skip"}

        except Exception as e:
            logger.error("remote_dev router error: %s", sanitize_sensitive_info(str(e)), exc_info=True)
            return {}  # 예외는 silently pass

    async def _send_reply(self, gateway: Any, chat_id: int, text: str) -> None:
        """Gateway를 통해 응답 발송"""
        try:
            send = getattr(gateway, 'send', None)
            if callable(send):
                result = send(chat_id, text)
                if hasattr(result, '__await__'):
                    await result
        except Exception as e:
            logger.warning("remote_dev: failed to send reply: %s", str(e))

    async def _handle_status(self, user_id: int, chat_id: int, args: str) -> str:
        """상태 조회"""
        stats = self.queue.get_stats()
        lines = [
            f"총 작업: {stats.get('total', 0)}",
            f"대기 중: {stats.get('queued', 0)}",
            f"실행 중: {stats.get('running', 0)}",
            f"승인 대기: {stats.get('waiting_approval', 0)}",
            f"완료: {stats.get('completed', 0)}",
            f"실패: {stats.get('failed', 0)}",
            f"취소: {stats.get('cancelled', 0)}",
        ]
        return f"📊 **원격 개발 시스템 상태**\n\n" + "\n".join(lines)

    async def _handle_investigate(self, user_id: int, chat_id: int, args: str) -> str:
        """조사 요청"""
        if not args or len(args.strip()) < 2:
            return "❌ 조사 대상을 명시하세요.\n예: /조사 프로젝트 구조"

        description = sanitize_sensitive_info(args.strip()[:200])
        task_id = _generate_task_id(user_id, 'investigate', description)

        task = TaskInfo(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            task_type='investigate',
            description=description,
            status=TaskStatus.QUEUED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            idempotency_key=f"investigate-{user_id}-{task_id}",
        )

        success, err = self.queue.upsert_task(task)
        if success:
            logger.info("remote_dev: investigate task registered: %s", task_id)
            return f"✅ 조사 작업 접수됨\n작업 ID: {task_id}\n대상: {description}"
        else:
            return f"⚠️ 중복 요청이 감지되었습니다 (이미 등록됨: {task_id})"

    async def _handle_task(self, user_id: int, chat_id: int, args: str) -> str:
        """작업 상태 조회"""
        task_id = args.strip()
        if not task_id:
            return "❌ 작업 ID를 명시하세요.\n예: /작업 task-abc123"

        task = self.queue.get_task(task_id)
        if task is None:
            return f"❌ 작업을 찾을 수 없습니다: {task_id}"

        if task.user_id != user_id:
            return f"❌ 이 작업에 접근할 권한이 없습니다 (작업 ID: {task_id})"

        status_emoji = {
            'queued': '⏳',
            'running': '🔄',
            'waiting_approval': '⏸️',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫',
        }
        emoji = status_emoji.get(task.status.value, '❓')

        msg = f"📋 **작업 정보**\n\n"
        msg += f"ID: {task.task_id}\n"
        msg += f"상태: {emoji} {task.status.value}\n"
        msg += f"유형: {task.task_type}\n"
        msg += f"생성: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        if task.description:
            msg += f"설명: {task.description[:100]}\n"
        if task.error_code:
            msg += f"오류: {task.error_code}\n"
            if task.error_summary:
                msg += f"요약: {task.error_summary}\n"

        return msg

    async def _handle_help(self, user_id: int, chat_id: int, args: str) -> str:
        """도움말"""
        msg = "📖 **원격 개발 명령어 도움말**\n\n"
        msg += "**사용 가능한 명령어:**\n\n"
        msg += "• `/상태` — 시스템 및 작업 대기열 상태 조회\n"
        msg += "• `/조사 <대상>` — 읽기 전용 조사 작업 요청\n"
        msg += "• `/작업 <task_id>` — 작업 상태 조회 (소유권 검증)\n"
        msg += "• `/실행 <설명>` — 실행 작업 요청 (승인 대기)\n"
        msg += "• `/도움말` — 이 도움말 다시 보기\n\n"
        msg += "**참고:**\n"
        msg += "- 모든 명령은 개인 대화에서만 사용 가능합니다.\n"
        msg += "- `/실행`은 승인 대기 상태로 등록됩니다.\n"
        return msg

    async def _handle_execute(self, user_id: int, chat_id: int, args: str) -> str:
        """실행 요청 (승인 대기)"""
        if not args or len(args.strip()) < 2:
            return "❌ 실행할 작업을 설명하세요.\n예: /실행 로그 파일 분석 요청"

        description = sanitize_sensitive_info(args.strip()[:200])
        task_id = _generate_task_id(user_id, 'execute', description)

        task = TaskInfo(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            task_type='execute',
            description=description,
            status=TaskStatus.WAITING_APPROVAL,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            idempotency_key=f"execute-{user_id}-{task_id}",
            approved=False,
        )

        success, err = self.queue.upsert_task(task)
        if success:
            logger.info("remote_dev: execute task registered for approval: %s", task_id)
            return (f"⏸️ 실행 작업이 승인 대기 중입니다\n"
                    f"작업 ID: {task_id}\n"
                    f"설명: {description}\n\n"
                    f"관리자의 승인이 필요합니다.")
        else:
            return f"⚠️ 중복 요청이 감지되었습니다 (이미 등록됨: {task_id})"

    async def _handle_approve(self, user_id: int, chat_id: int, args: str) -> str:
        """승인 요청 — WAITING_APPROVAL → approved=True"""
        task_id = args.strip()
        if not task_id:
            return "❌ 작업 ID를 명시하세요.\n예: /승인 task-abc123"

        task = self.queue.get_task(task_id)
        if task is None:
            return f"❌ 작업을 찾을 수 없습니다: {task_id}"

        if task.user_id != user_id:
            return f"❌ 이 작업에 접근할 권한이 없습니다 (작업 ID: {task_id})"

        if task.status != TaskStatus.WAITING_APPROVAL:
            return f"❌ 승인할 수 없는 상태입니다: {task.status.value}"

        success = self.queue.approve_task(task_id)
        if success:
            logger.info("remote_dev: task approved: %s", task_id)
            await self.notifier.emit(task_id, EventType.ACCEPTED, status="approved")
            return (f"✅ 작업이 승인되었습니다\n"
                    f"작업 ID: {task_id}\n"
                    f"상태: 실행 가능")
        else:
            return "⚠️ 이미 처리된 요청입니다 (중복 클릭 방지)"

    async def _handle_reject(self, user_id: int, chat_id: int, args: str) -> str:
        """거절 요청 — WAITING_APPROVAL → FAILED"""
        parts = args.strip().split(None, 1)
        task_id = parts[0] if parts else ""
        reason = parts[1] if len(parts) > 1 else "사유 없음"

        if not task_id:
            return "❌ 작업 ID를 명시하세요.\n예: /거절 task-abc123 사유"

        task = self.queue.get_task(task_id)
        if task is None:
            return f"❌ 작업을 찾을 수 없습니다: {task_id}"

        if task.user_id != user_id:
            return f"❌ 이 작업에 접근할 권한이 없습니다 (작업 ID: {task_id})"

        if task.status != TaskStatus.WAITING_APPROVAL:
            return f"❌ 거절할 수 없는 상태입니다: {task.status.value}"

        success = self.queue.reject_task(task_id, reason=sanitize_sensitive_info(reason))
        if success:
            logger.info("remote_dev: task rejected: %s", task_id)
            await self.notifier.emit(task_id, EventType.FAILED, error=sanitize_sensitive_info(reason))
            return f"❌ 작업이 거절되었습니다\n작업 ID: {task_id}\n사유: {sanitize_sensitive_info(reason)}"
        else:
            return "⚠️ 이미 처리된 요청입니다"

    async def _handle_cancel(self, user_id: int, chat_id: int, args: str) -> str:
        """취소 — QUEUED 또는 WAITING_APPROVAL → CANCELLED"""
        task_id = args.strip()
        if not task_id:
            return "❌ 작업 ID를 명시하세요.\n예: /취소 task-abc123"

        task = self.queue.get_task(task_id)
        if task is None:
            return f"❌ 작업을 찾을 수 없습니다: {task_id}"

        if task.user_id != user_id:
            return f"❌ 이 작업에 접근할 권한이 없습니다 (작업 ID: {task_id})"

        if task.status not in (TaskStatus.QUEUED, TaskStatus.WAITING_APPROVAL):
            return f"❌ 취소할 수 없는 상태입니다: {task.status.value}"

        success = self.queue.cancel_task(task_id)
        if success:
            logger.info("remote_dev: task cancelled: %s", task_id)
            return f"🚫 작업이 취소되었습니다\n작업 ID: {task_id}"
        else:
            return "⚠️ 이미 처리된 요청입니다"

    async def _handle_commands(self, user_id: int, chat_id: int, args: str) -> str:
        """명령 목록 표시"""
        return ("📖 **원격 개발 명령어 목록**\n\n"
                "**읽기 전용:**\n"
                "• `/상태` — 시스템 및 작업 대기열 상태 조회\n"
                "• `/작업 <task_id>` — 작업 상태 조회\n"
                "• `/상세 <task_id>` — 작업 상세 정보 조회\n"
                "• `/명령` — 이 도움말\n\n"
                "**쓰기 가능:**\n"
                "• `/실행 <설명>` — 실행 작업 요청 (승인 대기)\n"
                "• `/승인 <task_id>` — 작업 승인\n"
                "• `/취소 <task_id>` — 작업 취소\n\n"
                "**위험 (확인 필요):**\n"
                "• `/거절 <task_id> [이유]` — 작업 거절\n\n"
                "**참고:**\n"
                "- 모든 명령은 개인 대화에서만 사용 가능합니다.\n"
                "- 작업 ID는 본인의 작업만 접근 가능합니다.")

    async def _handle_detail(self, user_id: int, chat_id: int, args: str) -> str:
        """작업 상세 조회"""
        task_id = args.strip()
        if not task_id:
            return "❌ 작업 ID를 명시하세요.\n예: /상세 task-abc123"

        task = self.queue.get_task(task_id)
        if task is None:
            return f"❌ 작업을 찾을 수 없습니다: {task_id}"

        if task.user_id != user_id:
            return f"❌ 이 작업에 접근할 권한이 없습니다 (작업 ID: {task_id})"

        status_emoji = {
            'queued': '⏳',
            'running': '🔄',
            'waiting_approval': '⏸️',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '🚫',
        }
        emoji = status_emoji.get(task.status.value, '❓')

        lines = [
            f"📋 **작업 상세 정보**\n\n",
            f"ID: {task.task_id}",
            f"상태: {emoji} {task.status.value}",
            f"유형: {task.task_type}",
            f"생성: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"수정: {task.updated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"승인: {'✅' if task.approved else '❌'}",
        ]
        if task.description:
            desc = sanitize_sensitive_info(task.description)[:200]
            lines.append(f"설명: {desc}")
        if task.error_code:
            lines.append(f"오류 코드: {task.error_code}")
        if task.error_summary:
            lines.append(f"오류 요약: {sanitize_sensitive_info(task.error_summary)[:100]}")

        return "\n".join(lines)

    async def _handle_notification_status(self, user_id: int, chat_id: int, args: str) -> str:
        """알림 상태 조회 — /알림상태"""
        focus = get_focus_mode()
        status = focus.get_status()
        return (f"🔔 **알림 상태**\n\n"
                f"집중 모드: {'🔒 활성화됨' if status['enabled'] else '🔓 비활성화됨'}\n"
                f"억제된 알림: {status['suppressed_count']}건\n"
                f"최종 업데이트: {status['last_updated'][:19]}")

    async def _handle_focus_mode(self, user_id: int, chat_id: int, args: str) -> str:
        """집중 모드 제어 — /집중모드 켜기|끄기"""
        focus = get_focus_mode()
        args = args.strip()

        if not args:
            return ("❌ 작업을 지정하세요\n\n"
                    "• `/집중모드 켜기` — 집중 모드 시작\n"
                    "• `/집중모드 끄기` — 집중 모드 종료\n"
                    "• `/알림상태` — 알림 상태 확인")

        if args == "켜기":
            focus.enable()
            return "✅ 집중 모드가 시작되었습니다\n\n억제되는 알림:\n• 일반 작업 시작\n• 일반 작업 완료"
        elif args == "끄기":
            focus.disable()
            return "🔓 집중 모드가 종료되었습니다\n모든 알림이 정상적으로 전송됩니다."
        elif args == "요약":
            return focus.get_summary()
        else:
            return f"❌ 모르는 작업: {args}\n'/집중모드' 명령으로 도움말을 확인하세요."

    async def _handle_unknown(self, user_id: int, chat_id: int, command: str) -> str:
        """알 수 없는 명령어"""
        return f"❌ 알 수 없는 명령어: /{command}\n\n" \
               f"'/명령'을 입력하여 사용 가능한 명령어를 확인하세요."


# 싱글턴 인스턴스
_router_instance = None


def get_router() -> RemoteDevRouter:
    """라우터 인스턴스 반환 (싱글턴)"""
    global _router_instance
    if _router_instance is None:
        _router_instance = RemoteDevRouter()
    return _router_instance


async def pre_gateway_dispatch_handler(
    event: Any, source: Any, gateway: Any, **kwargs
) -> Dict[str, Any]:
    """
    pre_gateway_dispatch 훅 콜백 (플러그인 등록용).
    """
    return await get_router().handle(event, source, gateway, **kwargs)
