#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notification Focus Mode Module
알림 집중 모드: 비긴급 알림 억제, 긴급 알림 허용
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 집중 모드에서도 전송되는 긴급 알림 유형
CRITICAL_EVENT_TYPES = {"accepted", "failed", "approval_required"}
# 집중 모드 중 억제되는 일반 알림 유형
SUPPRESSED_EVENT_TYPES = {"started", "completed"}


class FocusMode:
    """알림 집중 모드 관리자"""

    CONFIG_DIR = Path.home() / ".hermes"
    CONFIG_FILE = CONFIG_DIR / "focus_mode.json"

    def __init__(self):
        self._enabled = False
        self._suppressed_count = 0
        self._suppressed_log: List[dict] = []
        self._lock = threading.Lock()
        self._load_config()

    def _load_config(self):
        """파일에서 설정 로드"""
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._enabled = data.get('enabled', False)
                    self._suppressed_count = data.get('suppressed_count', 0)
                    self._suppressed_log = data.get('suppressed_log', [])
        except Exception:
            pass

    def _save_config(self):
        """설정을 파일에 저장"""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                'enabled': self._enabled,
                'suppressed_count': self._suppressed_count,
                'suppressed_log': self._suppressed_log[-100:],
                'updated_at': datetime.now().isoformat(),
            }
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("focus_mode: save config failed: %s", str(e))

    def get_status(self) -> dict:
        """집중 모드 상태 반환"""
        return {
            'enabled': self._enabled,
            'suppressed_count': self._suppressed_count,
            'last_updated': datetime.now().isoformat(),
        }

    def enable(self) -> bool:
        """집중 모드 활성화"""
        with self._lock:
            self._enabled = True
            self._save_config()
            return True

    def disable(self) -> bool:
        """집중 모드 비활성화"""
        with self._lock:
            self._enabled = False
            self._save_config()
            return True

    def toggle(self) -> bool:
        """집중 모드 토글"""
        if self._enabled:
            return self.disable()
        return self.enable()

    def should_suppress(self, event_type: str) -> bool:
        """집중 모드 중 알림 억제 여부 판단"""
        if not self._enabled:
            return False
        # 긴급 알림은 항상 허용
        if event_type in CRITICAL_EVENT_TYPES:
            return False
        # 일반 알림은 억제
        return event_type in SUPPRESSED_EVENT_TYPES

    def record_suppressed(self, event_type: str, task_id: str, summary: str):
        """억제된 알림 기록"""
        with self._lock:
            self._suppressed_count += 1
            self._suppressed_log.append({
                'event_type': event_type,
                'task_id': task_id,
                'summary': summary,
                'timestamp': datetime.now().isoformat(),
            })
            self._save_config()

    def get_summary(self) -> str:
        """억제된 알림 요약 반환"""
        with self._lock:
            lines = [
                f"📊 **알림 집중 모드 요약**",
                f"",
                f"현재 상태: {'🔒 활성화됨' if self._enabled else '🔓 비활성화됨'}",
                f"억제된 알림 수: {self._suppressed_count}건",
            ]
            if self._suppressed_log:
                lines.append("")
                lines.append("**최근 억제된 알림:**")
                for item in self._suppressed_log[-5:]:
                    lines.append(
                        f"- [{item['timestamp'][:19]}] {item['event_type']}: {item['task_id'][:8]}..."
                    )
            return "\n".join(lines)

    def reset(self):
        """상태 초기화 (테스트용)"""
        with self._lock:
            self._enabled = False
            self._suppressed_count = 0
            self._suppressed_log = []
            self._save_config()


# 전역 인스턴스
_focus_mode: Optional[FocusMode] = None
_focus_lock = threading.Lock()


def get_focus_mode() -> FocusMode:
    """전역 FocusMode 인스턴스 반환 (싱글턴)"""
    global _focus_mode
    with _focus_lock:
        if _focus_mode is None:
            _focus_mode = FocusMode()
        return _focus_mode


def reset_focus_mode():
    """전역 인스턴스 초기화 (테스트용)"""
    global _focus_mode
    with _focus_lock:
        _focus_mode = None
    # 설정 파일도 삭제하여 다음 테스트에서 fresh 상태 보장
    try:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
    except Exception:
        pass
