#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
명령어 파서 모듈
Telegram 원격 개발 명령어 파싱 및 분류
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandLevel(Enum):
    """명령어 권한 레벨"""
    READ = 1      # 읽기 전용
    WRITE = 2     # 작성 가능
    EXECUTE = 3   # 실행 가능
    DANGER = 4    # 위험 명령


@dataclass
class CommandResult:
    """명령어 파싱 결과"""
    success: bool
    command: Optional[str] = None
    args: Optional[str] = None
    level: Optional[CommandLevel] = None
    error: Optional[str] = None
    requires_auth: bool = False

    def to_message(self) -> str:
        """사용자 메시지 생성"""
        if self.success:
            return f"✅ 명령어 분석 완료\n명령: {self.command}\n인자: {self.args or '없음'}\n레벨: {self.level.name}"
        else:
            return f"❌ 명령어 오류\n{self.error}"


class CommandParser:
    """명령어 파서 클래스"""

    # 최대 메시지 길이
    MAX_MESSAGE_LENGTH = 500

    # 허용된 명령어 정의
    ALLOWED_COMMANDS = {
        '상태': CommandLevel.READ,
        '조사': CommandLevel.READ,
        '실행': CommandLevel.EXECUTE,
        '작업': CommandLevel.READ,
        '도움말': CommandLevel.READ,
        '승인': CommandLevel.WRITE,
        '거절': CommandLevel.DANGER,
        '취소': CommandLevel.WRITE,
        '명령': CommandLevel.READ,
        '상세': CommandLevel.READ,
        '알림상태': CommandLevel.READ,
        '집중모드': CommandLevel.WRITE,
    }

    # 명령어 패턴 (앞뒤 공백 제거) - 유니코드 지원 (\w는 ASCII만 지원)
    COMMAND_PATTERN = re.compile(r'^/([^\s/]+)(?:\s+(.*))?$', re.IGNORECASE)

    # 봇 멘션 패턴
    BOT_MENTION_PATTERN = re.compile(r'@[\w\-]+(?:bot)?\s*', re.IGNORECASE)

    # 위험 문자 패턴 (명령어 주입 방지)
    DANGEROUS_PATTERNS = [
        r';\s*\w+',      # 세미콜론 후 명령
        r'&&\s*\w+',     # AND 연결
        r'\|\|\s*\w+',   # OR 연결
        r'\|\s*\w+',     # 파이프 연결
        r'\$\(',         # 명령 치환
        r'\${',         # 변수 치환
        r'`',            # 백틱
        r'\.\./',        # 상위 디렉터리 접근
        r'rm\s+-rf',     # 강제 삭제
        r'sudo',         # 관리자 권한
        r'chmod',        # 권한 변경
        r'mkdir\s+-p',   # 강제 디렉터리 생성
        r'>\s*',         # 출력 리다이렉트
        r'<\s*',         # 입력 리다이렉트
        r'&\s*$',        # 백그라운드 실행
    ]

    def __init__(self):
        self.dangerous_regex = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS]

    def parse(self, message: str) -> CommandResult:
        """
        메시지로부터 명령어 파싱

        Args:
            message: Telegram 메시지에서 추출한 텍스트

        Returns:
            CommandResult: 파싱 결과
        """
        # 1. 타입 검증
        if not isinstance(message, str):
            return CommandResult(
                success=False,
                error="메시지가 문자열이 아닙니다"
            )

        # 2. 길이 제한
        if len(message) > self.MAX_MESSAGE_LENGTH:
            return CommandResult(
                success=False,
                error=f"메시지 길이가 너무 깁니다 (최대 {self.MAX_MESSAGE_LENGTH}자)"
            )

        # 3. 인코딩 검증 (유효한 UTF-8)
        try:
            message.encode('utf-8')
        except UnicodeEncodeError:
            return CommandResult(
                success=False,
                error="잘못된 인코딩이 감지되었습니다"
            )

        message = message.strip()

        # 4. 봇 멘션 처리
        message = self.BOT_MENTION_PATTERN.sub('', message).strip()

        # 5. 빈 메시지 체크
        if not message:
            return CommandResult(
                success=False,
                error="메시지가 비어있습니다"
            )

        # 명령어 형식 확인 (/로 시작)
        if not message.startswith('/'):
            return CommandResult(
                success=False,
                error="명령어는 '/'로 시작해야 합니다"
            )

        # 명령어 패턴 매칭
        match = self.COMMAND_PATTERN.match(message)
        if not match:
            return CommandResult(
                success=False,
                error="명령어 형식이 올바르지 않습니다"
            )

        command = match.group(1).lower()
        args = match.group(2)

        # 위험 문자 검사
        if self._has_dangerous_patterns(args or ''):
            return CommandResult(
                success=False,
                error="위험한 문자가 감지되었습니다",
                level=CommandLevel.DANGER
            )

        # 허용된 명령어 확인
        if command not in self.ALLOWED_COMMANDS:
            allowed = ', '.join(self.ALLOWED_COMMANDS.keys())
            return CommandResult(
                success=False,
                error=f"허용되지 않은 명령어입니다. 허용 명령어: {allowed}"
            )

        # 인자 검증
        if command == '조사' and not args:
            return CommandResult(
                success=False,
                error="조사 대상이 지정되지 않았습니다. 예: /조사 database"
            )

        if command == '실행' and not args:
            return CommandResult(
                success=False,
                error="작업 설명이 필요합니다. 예: /실행 파일생성 테스트"
            )

        return CommandResult(
            success=True,
            command=command,
            args=args,
            level=self.ALLOWED_COMMANDS[command],
            requires_auth=(command == '실행')
        )

    def _has_dangerous_patterns(self, text: str) -> bool:
        """위험 문자 패턴 검사"""
        for pattern in self.dangerous_regex:
            if pattern.search(text):
                return True
        return False

    def get_allowed_commands(self) -> list:
        """허용된 명령어 목록 반환"""
        return list(self.ALLOWED_COMMANDS.keys())

    def validate_args(self, command: str, args: str) -> tuple:
        """
        인자 검증

        Returns:
            tuple: (is_valid: bool, error_message: Optional[str])
        """
        if not args or not args.strip():
            return False, "인자가 필요합니다"

        # SQL Injection 방지
        sql_patterns = [r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\b', r';\s*']
        for pattern in sql_patterns:
            if re.search(pattern, args, re.IGNORECASE):
                return False, "위험한 문자가 감지되었습니다"

        # 파일 경로 검증 (상대 경로만 허용)
        if '..' in args or args.startswith('/'):
            return False, "절대 경로 또는 상위 디렉터리 접근은 허용되지 않습니다"

        return True, None
