#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
인증 관리자 모듈
Telegram 사용자 인증 및 권한 관리
"""

import os
import json
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Set
from datetime import datetime, timedelta


class AuthStatus(Enum):
    """인증 상태"""
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass
class AuthResult:
    """인증 결과"""
    status: AuthStatus
    user_id: Optional[int] = None
    chat_id: Optional[int] = None
    level: Optional[int] = None
    error: Optional[str] = None
    requires_password: bool = False
    requires_auth: bool = False

    def to_message(self) -> str:
        """사용자 메시지 생성"""
        if self.status == AuthStatus.SUCCESS:
            return f"✅ 인증 완료\n사용자 ID: {self.user_id}\n채팅 ID: {self.chat_id}\n권한 레벨: {self.level}"
        elif self.status == AuthStatus.BLOCKED:
            return f"🔒 인증 차단됨\n{self.error}"
        else:
            return f"❌ 인증 실패\n{self.error}"


class AuthManager:
    """인증 관리자 클래스"""

    # 설정 파일 경로
    CONFIG_DIR = Path.home() / ".hermes"
    AUTH_CONFIG_FILE = CONFIG_DIR / "remote_auth.json"
    BLOCK_CONFIG_FILE = CONFIG_DIR / "remote_blocks.json"

    # 허용된 대화 유형 (개인 대화만)
    ALLOWED_CHAT_TYPES = {'private'}

    def __init__(self):
        self.allowed_users: Set[int] = set()
        self.allowed_chats: Set[int] = set()
        self.secret_word: str = ""
        self.failed_attempts: dict = {}  # user_id -> [(timestamp, success)]
        self.blocked_until: dict = {}    # user_id -> timestamp
        self._lock = threading.Lock()    # 동시성 제어

        self._load_config()
        self._load_blocks()

    def _load_config(self):
        """인증 설정 로드"""
        try:
            if self.AUTH_CONFIG_FILE.exists():
                with open(self.AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.allowed_users = set(config.get('allowed_user_ids', []))
                    self.allowed_chats = set(config.get('allowed_chat_ids', []))
                    # 비밀단어는 환경변수에서 가져옴 (하드코딩 금지)
                    self.secret_word = os.getenv('REMOTE_DEV_SECRET_WORD', '')
            else:
                # 기본 설정 (환경변수에서 가져오기)
                self._load_from_env()
        except Exception as e:
            # 설정 로드 실패 시 기본 거부
            self.allowed_users.clear()
            self.allowed_chats.clear()
            self.secret_word = ''

    def _load_from_env(self):
        """환경변수에서 설정 로드"""
        # 사용자 ID 목록 (쉼표 구분)
        user_ids = os.getenv('REMOTE_DEV_ALLOWED_USERS', '')
        if user_ids:
            self.allowed_users = set(int(x.strip()) for x in user_ids.split(',') if x.strip().isdigit())

        # 채팅 ID 목록 (쉼표 구분)
        chat_ids = os.getenv('REMOTE_DEV_ALLOWED_CHATS', '')
        if chat_ids:
            self.allowed_chats = set(int(x.strip()) for x in chat_ids.split(',') if x.strip().isdigit())

        # 비밀단어
        self.secret_word = os.getenv('REMOTE_DEV_SECRET_WORD', '')

    def _load_blocks(self):
        """차단 상태 로드 (영속성)"""
        try:
            if self.BLOCK_CONFIG_FILE.exists():
                with open(self.BLOCK_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    blocks = json.load(f)
                    self.blocked_until = {
                        int(k): datetime.fromisoformat(v)
                        for k, v in blocks.items()
                        if datetime.fromisoformat(v) > datetime.now()
                    }
        except Exception:
            pass

    def _save_blocks(self):
        """차단 상태 저장 (영속성)"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            blocks = {
                str(k): v.isoformat()
                for k, v in self.blocked_until.items()
            }
            with open(self.BLOCK_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(blocks, f, ensure_ascii=False)
        except Exception:
            pass

    def save_config(self):
        """설정 저장"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config = {
                'allowed_user_ids': list(self.allowed_users),
                'allowed_chat_ids': list(self.allowed_chats),
                # 비밀단어는 저장하지 않음 (환경변수 사용)
            }
            with open(self.AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[AuthManager] 설정 저장 실패: {e}")

    def _validate_types(self, user_id, chat_id) -> tuple:
        """
        사용자 ID와 chat_id 타입 검증
        bool은 int의 하위 유형이므로 명시적으로 거부
        """
        # bool 체크 (Python에서 bool은 int의 서브클래스)
        if isinstance(user_id, bool) or isinstance(chat_id, bool):
            return False, "사용자 ID와 chat_id는布尔类型을 허용하지 않습니다"

        # 정수 타입 체크
        if not isinstance(user_id, int):
            return False, f"사용자 ID는 정수여야 합니다 (type: {type(user_id).__name__})"
        if not isinstance(chat_id, int):
            return False, f"chat_id는 정수여야 합니다 (type: {type(chat_id).__name__})"

        # 음수 체크
        if user_id < 0:
            return False, "사용자 ID는 양수여야 합니다"
        if chat_id < 0:
            return False, "chat_id는 양수여야 합니다"

        return True, None

    def authenticate(
        self,
        user_id,
        chat_id,
        chat_type: str = 'private',
        secret_word: Optional[str] = None
    ) -> AuthResult:
        """
        사용자 인증

        Args:
            user_id: Telegram 사용자 ID (정수)
            chat_id: Telegram 채팅 ID (정수)
            chat_type: Telegram 대화 유형 ('private', 'group', 'supergroup', 'channel')
            secret_word: 비밀단어 (선택사항)

        Returns:
            AuthResult: 인증 결과
        """
        # 1. 타입 검증
        type_valid, type_error = self._validate_types(user_id, chat_id)
        if not type_valid:
            return AuthResult(
                status=AuthStatus.FAILED,
                user_id=user_id if isinstance(user_id, int) else None,
                chat_id=chat_id if isinstance(chat_id, int) else None,
                error=type_error
            )

        # 2. 대화 유형 검증 (개인 대화만 허용)
        if chat_type not in self.ALLOWED_CHAT_TYPES:
            return AuthResult(
                status=AuthStatus.FAILED,
                user_id=user_id,
                chat_id=chat_id,
                error=f"원격 개발 명령은 개인 대화에서만 허용됩니다 (현재: {chat_type})"
            )

        # 3. 차단 상태 확인 (락 사용)
        with self._lock:
            if self._is_blocked(user_id):
                return AuthResult(
                    status=AuthStatus.BLOCKED,
                    user_id=user_id,
                    chat_id=chat_id,
                    error="너무 많은 인증 실패로 일시 차단되었습니다"
                )

            # 4. 기본 검증
            if not self.allowed_users and not self.allowed_chats:
                # 설정이 없으면 기본 거부 (안전 모드)
                return AuthResult(
                    status=AuthStatus.FAILED,
                    user_id=user_id,
                    chat_id=chat_id,
                    error="인증 설정이 없습니다. 관리자에게 문의하세요"
                )

            # 5. 허용된 사용자/채팅 확인
            user_allowed = user_id in self.allowed_users if self.allowed_users else False
            chat_allowed = chat_id in self.allowed_chats if self.allowed_chats else False

            if not user_allowed and not chat_allowed:
                self._record_failure(user_id)
                return AuthResult(
                    status=AuthStatus.FAILED,
                    user_id=user_id,
                    chat_id=chat_id,
                    error="인증되지 않은 사용자입니다"
                )

            # 6. 비밀단어 필요성 확인
            if self.secret_word and secret_word != self.secret_word:
                # 이미 허용된 사용자/채팅이면 비밀단어 없이 접근 가능
                if user_allowed or chat_allowed:
                    return AuthResult(
                        status=AuthStatus.SUCCESS,
                        user_id=user_id,
                        chat_id=chat_id,
                        level=1,  # 기본 레벨
                        requires_auth=False
                    )
                else:
                    self._record_failure(user_id)
                    return AuthResult(
                        status=AuthStatus.FAILED,
                        user_id=user_id,
                        chat_id=chat_id,
                        error="비밀단어가 필요합니다",
                        requires_auth=True
                    )

            # 7. 성공
            self._clear_failures(user_id)
            return AuthResult(
                status=AuthStatus.SUCCESS,
                user_id=user_id,
                chat_id=chat_id,
                level=3 if (user_allowed and chat_allowed) else 1,
                requires_auth=False
            )

    def verify_secret_word(self, user_id: int, secret_word: str) -> AuthResult:
        """
        비밀단어 검증

        Args:
            user_id: 사용자 ID
            secret_word: 입력된 비밀단어

        Returns:
            AuthResult: 검증 결과
        """
        # 타입 검증
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            return AuthResult(
                status=AuthStatus.FAILED,
                error="올바르지 않은 사용자 ID 형식입니다"
            )

        if not self.secret_word:
            return AuthResult(
                status=AuthStatus.SUCCESS,
                user_id=user_id,
                level=3,
                error="비밀단어 설정이 없습니다"
            )

        # 동시성 제어
        with self._lock:
            if secret_word.strip().lower() == self.secret_word.strip().lower():
                self._clear_failures(user_id)
                return AuthResult(
                    status=AuthStatus.SUCCESS,
                    user_id=user_id,
                    level=3
                )
            else:
                self._record_failure(user_id)
                remaining = 3 - self._get_failure_count(user_id)
                return AuthResult(
                    status=AuthStatus.FAILED,
                    user_id=user_id,
                    error=f"비밀단어가 올바르지 않습니다. 남은 시도: {remaining}회"
                )

    def _is_blocked(self, user_id: int) -> bool:
        """차단 상태 확인"""
        if user_id not in self.blocked_until:
            return False
        return datetime.now() < self.blocked_until[user_id]

    def _record_failure(self, user_id: int):
        """인증 실패 기록"""
        if user_id not in self.failed_attempts:
            self.failed_attempts[user_id] = []
        self.failed_attempts[user_id].append({
            'timestamp': datetime.now().isoformat(),
            'success': False
        })
        # 3회 실패 시 1시간 차단
        if len(self.failed_attempts[user_id]) >= 3:
            self.blocked_until[user_id] = datetime.now() + timedelta(hours=1)
            self._save_blocks()

    def _clear_failures(self, user_id: int):
        """인증 성공 시 실패 기록 삭제"""
        if user_id in self.failed_attempts:
            self.failed_attempts[user_id] = []
        if user_id in self.blocked_until:
            del self.blocked_until[user_id]
            self._save_blocks()

    def _get_failure_count(self, user_id: int) -> int:
        """최근 1시간 이내 실패 횟수"""
        if user_id not in self.failed_attempts:
            return 0
        cutoff = datetime.now() - timedelta(hours=1)
        return sum(
            1 for attempt in self.failed_attempts[user_id]
            if datetime.fromisoformat(attempt['timestamp']) > cutoff
        )

    def add_allowed_user(self, user_id: int):
        """허용된 사용자 추가"""
        if not isinstance(user_id, int) or isinstance(user_id, bool):
            raise ValueError("user_id는 정수여야 합니다")
        self.allowed_users.add(user_id)
        self.save_config()

    def add_allowed_chat(self, chat_id: int):
        """허용된 채팅 추가"""
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            raise ValueError("chat_id는 정수여야 합니다")
        self.allowed_chats.add(chat_id)
        self.save_config()

    def remove_allowed_user(self, user_id: int):
        """허용된 사용자 제거"""
        self.allowed_users.discard(user_id)
        self.save_config()

    def remove_allowed_chat(self, chat_id: int):
        """허용된 채팅 제거"""
        self.allowed_chats.discard(chat_id)
        self.save_config()

    def unblock_user(self, user_id: int):
        """사용자 차단 해제"""
        if user_id in self.blocked_until:
            del self.blocked_until[user_id]
            self._save_blocks()
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]

    def get_config(self) -> dict:
        """현재 설정 반환 (민감정보 제외)"""
        return {
            'allowed_user_count': len(self.allowed_users),
            'allowed_chat_count': len(self.allowed_chats),
            'secret_word_set': bool(self.secret_word),
            'blocked_users': len(self.blocked_until),
        }
