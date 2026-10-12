#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
작업 대기열 모듈
SQLite 기반 영속 작업 관리, 상태 전이 검증, 중복 방지
"""

import asyncio
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiosqlite


# ============================================================
# 상수 및 정의
# ============================================================

# SQLite 데이터베이스 경로
DATA_DIR = Path.home() / ".hermes"
TASK_DB_FILE = DATA_DIR / "remote_tasks.db"

# 민감정보 매핑 패턴 (regex → 교체 문자열)
SENSITIVE_PATTERNS = [
    # Telegram Bot Token (13자리 숫자:AAAAA...)
    (re.compile(r'\d{13}:[A-Za-z0-9_-]{35}'), '[BOT_TOKEN]'),
    # OpenRouter API Key
    (re.compile(r'sk-or-v1-[a-f0-9]{64}'), '[OPENROUTER_KEY]'),
    # OpenAI 스타일 키
    (re.compile(r'sk-[A-Za-z0-9_-]{20,}'), '[API_KEY]'),
    # Gemini API Key
    (re.compile(r'AQ\.[A-Za-z0-9_-]{40,}'), '[GEMINI_KEY]'),
    # Notion API Key
    (re.compile(r'ntn_[a-zA-Z0-9]{20,}'), '[NOTION_KEY]'),
    # 환경변수 참조
    (re.compile(r'\$\{[A-Z_]+\}'), '[ENV_VAR]'),
    # 비밀단어 (기본값 '준' 또는 유사 패턴)
    (re.compile(r'\b준\b'), '[SECRET_WORD]'),
    # Credit card pattern
    (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), '[CARD]'),
]


# ============================================================
# Enum 및 Dataclass
# ============================================================

class TaskStatus(Enum):
    """작업 상태"""
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 상태 전이 허용 테이블 (현재 상태 → 허용되는 다음 상태)
VALID_TRANSITIONS: Dict[str, set] = {
    TaskStatus.QUEUED.value: {
        TaskStatus.RUNNING.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.RUNNING.value: {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.WAITING_APPROVAL.value: {
        TaskStatus.RUNNING.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    },
    TaskStatus.COMPLETED.value: set(),
    TaskStatus.FAILED.value: set(),
    TaskStatus.CANCELLED.value: set(),
}


class Priority(Enum):
    """작업 우선순위"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class TaskInfo:
    """작업 정보"""
    task_id: str
    user_id: int
    chat_id: int
    task_type: str          # 'status', 'investigate', 'execute'
    description: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    idempotency_key: str
    approved: bool = False
    error_code: Optional[str] = None
    error_summary: Optional[str] = None
    expiry_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'task_type': self.task_type,
            'description': self.description,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'idempotency_key': self.idempotency_key,
            'approved': self.approved,
            'error_code': self.error_code,
            'error_summary': self.error_summary,
            'expiry_time': self.expiry_time.isoformat() if self.expiry_time else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskInfo':
        return cls(
            task_id=data['task_id'],
            user_id=data['user_id'],
            chat_id=data['chat_id'],
            task_type=data['task_type'],
            description=data['description'],
            status=TaskStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            idempotency_key=data['idempotency_key'],
            approved=data.get('approved', False),
            error_code=data.get('error_code'),
            error_summary=data.get('error_summary'),
            expiry_time=datetime.fromisoformat(data['expiry_time']) if data.get('expiry_time') else None,
        )


# ============================================================
# 민감정보 마스킹
# ============================================================

def sanitize_sensitive_info(text: str) -> str:
    """민감정보가 포함된 텍스트를 마스킹"""
    if not isinstance(text, str):
        return text
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_error(error: Optional[Exception]) -> Optional[str]:
    """예외 객체에서 민감정보 제거"""
    if error is None:
        return None
    msg = str(error)
    return sanitize_sensitive_info(msg)


# ============================================================
# 동기 SQLite 래퍼 (읽기 전용 운영용)
# ============================================================

class TaskQueueDB:
    """SQLite 기반 작업 저장소 (동기 래퍼)"""

    def __init__(self, db_path: Path = TASK_DB_FILE):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """테이블 생성 (기존 데이터 삭제 금지)"""
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id      TEXT PRIMARY KEY,
                        user_id      INTEGER NOT NULL,
                        chat_id      INTEGER NOT NULL,
                        task_type    TEXT NOT NULL,
                        description  TEXT NOT NULL,
                        status       TEXT NOT NULL,
                        created_at   TEXT NOT NULL,
                        updated_at   TEXT NOT NULL,
                        idempotency_key TEXT UNIQUE,
                        approved     INTEGER NOT NULL DEFAULT 0,
                        error_code   TEXT,
                        error_summary TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_status
                    ON tasks (status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_user
                    ON tasks (user_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_idem
                    ON tasks (idempotency_key)
                """)
                conn.commit()
            finally:
                conn.close()

    def upsert_task(self, task: TaskInfo) -> tuple:
        """작업 등록 (idempotency_key 중복 시 (False, 'duplicate') 반환)"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT task_id FROM tasks WHERE idempotency_key = ?",
                    (task.idempotency_key,)
                )
                if cur.fetchone() is not None:
                    return (False, 'duplicate')

                conn.execute(
                    """INSERT INTO tasks
                       (task_id, user_id, chat_id, task_type, description,
                        status, created_at, updated_at, idempotency_key,
                        approved, error_code, error_summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.task_id, task.user_id, task.chat_id,
                        task.task_type, sanitize_sensitive_info(task.description),
                        task.status.value, task.created_at.isoformat(),
                        task.updated_at.isoformat(), task.idempotency_key,
                        int(task.approved), task.error_code,
                        sanitize_error_str(task.error_summary),
                    )
                )
                conn.commit()
                return (True, None)
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_task(row)
            finally:
                conn.close()

    def list_tasks(self, status: Optional[TaskStatus] = None,
                   user_id: Optional[int] = None,
                   limit: int = 50) -> List[TaskInfo]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                where = []
                params = []
                if status:
                    where.append("status = ?")
                    params.append(status.value)
                if user_id:
                    where.append("user_id = ?")
                    params.append(user_id)
                sql = "SELECT * FROM tasks"
                if where:
                    sql += " WHERE " + " AND ".join(where)
                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                cur = conn.execute(sql, params)
                return [self._row_to_task(r) for r in cur.fetchall()]
            finally:
                conn.close()

    def update_status(self, task_id: str, new_status: TaskStatus,
                      error_code: Optional[str] = None,
                      error_summary: Optional[str] = None) -> bool:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                )
                row = cur.fetchone()
                if row is None:
                    return False
                current = row[0]
                allowed = VALID_TRANSITIONS.get(current, set())
                if new_status.value not in allowed:
                    return False
                now = datetime.now().isoformat()
                conn.execute(
                    """UPDATE tasks SET status = ?, updated_at = ?,
                       error_code = ?, error_summary = ?
                       WHERE task_id = ?""",
                    (new_status.value, now, error_code,
                     sanitize_error_str(error_summary), task_id)
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def approve_task(self, task_id: str) -> bool:
        """작업 승인 — WAITING_APPROVAL에서 RUNNING으로 전환 (중복 방지 포함)"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT status, approved FROM tasks WHERE task_id = ?", (task_id,)
                )
                row = cur.fetchone()
                if row is None:
                    return False
                status, approved = row[0], row[1]
                # 이미 승인된 작업은 거부 (중복 방지)
                if approved:
                    return False
                if status != TaskStatus.WAITING_APPROVAL.value:
                    return False
                conn.execute(
                    "UPDATE tasks SET approved = 1, updated_at = ? WHERE task_id = ?",
                    (datetime.now().isoformat(), task_id)
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def reject_task(self, task_id: str, reason: Optional[str] = None) -> bool:
        """작업 거절 — WAITING_APPROVAL → FAILED"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
                )
                row = cur.fetchone()
                if row is None or row[0] != TaskStatus.WAITING_APPROVAL.value:
                    return False
                now = datetime.now().isoformat()
                conn.execute(
                    "UPDATE tasks SET status = ?, approved = 0, updated_at = ?, "
                    "error_code = ?, error_summary = ? WHERE task_id = ?",
                    (TaskStatus.FAILED.value, now, "rejected", 
                     sanitize_error_str(reason), task_id)
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def expire_pending_tasks(self, max_age_seconds: int = 3600) -> int:
        """만료된 승인 대기 작업 자동 FAILED 처리. 반환: 만료된 작업 수"""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cutoff = (datetime.now() - timedelta(seconds=max_age_seconds)).isoformat()
                cur = conn.execute(
                    "SELECT task_id FROM tasks WHERE status = ? AND updated_at < ?",
                    (TaskStatus.WAITING_APPROVAL.value, cutoff)
                )
                expired = [row[0] for row in cur.fetchall()]
                if expired:
                    placeholders = ",".join("?" * len(expired))
                    now = datetime.now().isoformat()
                    conn.execute(
                        f"UPDATE tasks SET status = ?, updated_at = ?, "
                        f"error_code = ?, error_summary = ? "
                        f"WHERE task_id IN ({placeholders})",
                        (TaskStatus.FAILED.value, now, "expired", "승인 만료", *expired)
                    )
                    conn.commit()
                return len(expired)
            finally:
                conn.close()

    def cancel_task(self, task_id: str) -> bool:
        return self.update_status(task_id, TaskStatus.CANCELLED)

    def get_stats(self) -> dict:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT status, COUNT(*) FROM tasks GROUP BY status"
                )
                stats = {'total': 0}
                for status, count in cur.fetchall():
                    stats[status] = count
                    stats['total'] += count
                return stats
            finally:
                conn.close()

    def _row_to_task(self, row) -> TaskInfo:
        cols = ['task_id','user_id','chat_id','task_type','description',
                'status','created_at','updated_at','idempotency_key',
                'approved','error_code','error_summary']
        data = dict(zip(cols, row))
        data['approved'] = bool(data.get('approved', 0))
        return TaskInfo.from_dict(data)


def sanitize_error_str(error_summary: Optional[str]) -> Optional[str]:
    """문자열 에러 요약 마스킹"""
    if error_summary is None:
        return None
    return sanitize_sensitive_info(error_summary)


# ============================================================
# 비동기 래퍼 (aiosqlite 기반)
# ============================================================

class AsyncTaskQueue:
    """aiosqlite 기반 비동기 작업 대기열"""

    def __init__(self, db_path: Path = TASK_DB_FILE):
        self.db_path = db_path

    async def _get_conn(self) -> aiosqlite.Connection:
        """새 연결 반환 (각 메서드에서 사용 후 닫힘)"""
        return aiosqlite.connect(str(self.db_path))

    async def initialize(self):
        """DB 초기화 (테이블 생성, 기존 데이터 보존)"""
        conn = await self._get_conn()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id        TEXT PRIMARY KEY,
                user_id        INTEGER NOT NULL,
                chat_id        INTEGER NOT NULL,
                task_type      TEXT NOT NULL,
                description    TEXT NOT NULL,
                status         TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                approved       INTEGER NOT NULL DEFAULT 0,
                error_code     TEXT,
                error_summary  TEXT
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_idem ON tasks(idempotency_key)")
        await conn.commit()

    async def close(self):
        pass  # 각 메서드에서 연결을 닫음

    async def add_task(self, task: TaskInfo) -> Tuple[bool, Optional[str]]:
        """
        작업 등록.
        반환: (성공 여부, 오류 메시지)
        idempotency_key 중복 시 (False, 'duplicate') 반환.
        """
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT task_id FROM tasks WHERE idempotency_key = ?",
                (task.idempotency_key,)
            )
            if await cur.fetchone() is not None:
                await conn.close()
                return (False, "duplicate")

            await conn.execute(
                """INSERT INTO tasks
                   (task_id, user_id, chat_id, task_type, description,
                    status, created_at, updated_at, idempotency_key,
                    approved, error_code, error_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.user_id, task.chat_id,
                    task.task_type, sanitize_sensitive_info(task.description),
                    task.status.value, task.created_at.isoformat(),
                    task.updated_at.isoformat(), task.idempotency_key,
                    int(task.approved), task.error_code,
                    sanitize_error_str(task.error_summary),
                )
            )
            await conn.commit()
            await conn.close()
            return (True, None)
        except Exception as e:
            await conn.rollback()
            await conn.close()
            return (False, str(e))

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return self._row_to_task(row)
        finally:
            await conn.close()

    async def list_tasks(self, status: Optional[TaskStatus] = None,
                         user_id: Optional[int] = None,
                         limit: int = 50) -> List[TaskInfo]:
        conn = await self._get_conn()
        try:
            where = []
            params = []
            if status:
                where.append("status = ?")
                params.append(status.value)
            if user_id:
                where.append("user_id = ?")
                params.append(user_id)
            sql = "SELECT * FROM tasks"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
            return [self._row_to_task(r) for r in rows]
        finally:
            await conn.close()

    async def transition(self, task_id: str, new_status: TaskStatus,
                         error_code: Optional[str] = None,
                         error_summary: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """상태 전이. 허용되지 않은 전이는 False 반환."""
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cur.fetchone()
            if row is None:
                await conn.close()
                return (False, "not_found")
            current = row[0]
            allowed = VALID_TRANSITIONS.get(current, set())
            if new_status.value not in allowed:
                await conn.close()
                return (False, f"invalid_transition:{current}->{new_status.value}")

            await conn.execute(
                """UPDATE tasks SET status = ?, updated_at = ?,
                   error_code = ?, error_summary = ?
                   WHERE task_id = ?""",
                (new_status.value, datetime.now().isoformat(),
                 error_code, sanitize_error_str(error_summary), task_id)
            )
            await conn.commit()
            await conn.close()
            return (True, None)
        except Exception as e:
            await conn.rollback()
            await conn.close()
            return (False, str(e))

    async def approve(self, task_id: str) -> Tuple[bool, Optional[str]]:
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cur.fetchone()
            if row is None or row[0] != TaskStatus.WAITING_APPROVAL.value:
                await conn.close()
                return (False, "not_waiting_approval")
            await conn.execute(
                "UPDATE tasks SET approved = 1, updated_at = ? WHERE task_id = ?",
                (datetime.now().isoformat(), task_id)
            )
            await conn.commit()
            await conn.close()
            return (True, None)
        except Exception as e:
            await conn.rollback()
            await conn.close()
            return (False, str(e))

    async def cancel(self, task_id: str) -> Tuple[bool, Optional[str]]:
        return await self.transition(task_id, TaskStatus.CANCELLED)

    async def get_stats(self) -> dict:
        conn = await self._get_conn()
        try:
            cur = await conn.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            )
            rows = await cur.fetchall()
            stats = {'total': 0}
            for status, count in rows:
                stats[status] = count
                stats['total'] += count
            return stats
        finally:
            await conn.close()

    @staticmethod
    def _row_to_task(row) -> TaskInfo:
        cols = ['task_id','user_id','chat_id','task_type','description',
                'status','created_at','updated_at','idempotency_key',
                'approved','error_code','error_summary']
        data = dict(zip(cols, row))
        return TaskInfo.from_dict(data)


# ============================================================
# 공개 API
# ============================================================

# 글로벌 동기 인스턴스 (단일ton)
_sync_instance: Optional[TaskQueueDB] = None
_sync_lock = threading.Lock()


def get_task_queue(db_path: Optional[Path] = None) -> TaskQueueDB:
    """글로벌 동기 작업 대기열 인스턴스 반환"""
    global _sync_instance
    path = db_path or TASK_DB_FILE
    with _sync_lock:
        if _sync_instance is None or _sync_instance.db_path != path:
            _sync_instance = TaskQueueDB(path)
        return _sync_instance


def reset_task_queue():
    """테스트용: 글로벌 인스턴스 초기화"""
    global _sync_instance
    with _sync_lock:
        _sync_instance = None
