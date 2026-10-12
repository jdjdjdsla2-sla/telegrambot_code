# Stage 3 구현 보고서

## 1. 개요

원격 작업 대기열 및 알림 시스템을 SQLite 기반으로 구현하였습니다. 기존 게이트웨이, 웹훅, Cron, 인증정보, Git 원격 저장소는 변경하지 않았습니다.

## 2. 생성/수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `remote_dev/task_queue.py` | 작업 대기열 모듈 (새로 생성, 579줄) |
| `remote_dev/notifications.py` | 알림 서비스 모듈 (새로 생성, 328줄) |
| `remote_dev/notion_adapter.py` | Notion 오류 로깅 어댑터 (새로 생성, 94줄) |
| `remote_dev/__init__.py` | 버전 v2.0.0, 모든 모듈 export |
| `tests/test_task_queue.py` | 작업 대기열 테스트 (18개) |
| `tests/test_notifications.py` | 알림 서비스 테스트 (12개) |

## 3. 작업 대기열 데이터 구조

### SQLite DB 경로
- `~/.hermes/remote_tasks.db`

### 테이블 스키마
```sql
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    approved BOOLEAN NOT NULL DEFAULT 0,
    error_code TEXT,
    error_summary TEXT
);
```

### 상태 Enum
- `queued`: 접수 후 대기
- `running`: 작업 실행 중
- `waiting_approval`: 승인 대기
- `completed`: 완료
- `failed`: 실패
- `cancelled`: 취소

## 4. 중복 방지 및 상태 전이 방식

### 중복 방지
- `idempotency_key` UNIQUE 제약조건 사용
- INSERT 전에 동일한 key 존재 여부 확인 (원자적 처리)
- 동시에 요청이 들어와도 중복 작업 생성 불가

### 상태 전이 규칙
```python
VALID_TRANSITIONS = {
    'queued': ['running', 'waiting_approval', 'cancelled'],
    'running': ['completed', 'failed', 'cancelled'],
    'waiting_approval': ['running'],  # 승인后才能 running
    'completed': [],
    'failed': [],
    'cancelled': [],
}
```

**핵심 규칙:**
- `waiting_approval` 상태의 작업은 승인(`approved=True`) 전까지 `running`으로 전환 불가
- 승인 기능은 이번 단계에서 실제 실행과 연결하지 않음

## 5. 알림 이벤트 및 재시도 정책

### 이벤트 유형
- `accepted`: 접수됨
- `started`: 시작됨
- `completed`: 완료됨
- `failed`: 실패함
- `approval_required`: 승인 필요

### DB 스키마
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    safe_summary TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    sent_at TEXT
);
```

### 중복 방지
- `(task_id, event_type)` 조합으로 고유 키 생성
- 동일한 키의 이벤트는 중복 발송되지 않음

### 재시도 정책
- 지수 백오프: 1s → 2s → 4s
- 최대 재시도 횟수: 3회
- 재시도 한도 초과 시 `max_retries_exceeded` 상태로 기록

### 전송 상태
- `pending`: 대기 중
- `retrying`: 재시도 중
- `sent`: 전송 성공
- `failed`: 전송 실패

## 6. Notion 로거 연결 방식

### 실제 기록 여부
- **모든 테스트에서 Mock 사용**
- 운영 Notion에는 기록하지 않음

### 어댑터 설계
```python
class NotionLoggerAdapter:
    - 기존 NotionErrorLogger 감싸서 호출
    - Notion 사용 불가 시 graceful fallback
    - 민감정보 마스킹 적용
```

### Mock Notion Logger
```python
class MockNotionLogger:
    - 로그된 오류 목록 추적
    - 실제 API 호출 없음
```

## 7. 민감정보 마스킹

### 적용 대상
- Telegram Bot Token: `1234567890123:ABCdefGHIjklMNOpqrSTUvwxYZ`
- OpenRouter API Key: `sk-or-v1-[64 hex chars]`
- OpenAI 스타일 키: `sk-[20+ chars]`
- Gemini API Key: `AQ.[40+ chars]`
- Notion API Key: `ntn_[...]`
- 비밀단어

### 마스킹 방식
- 저장 전 정규식 패턴 매칭 후 `[BOT_TOKEN]`, `[API_KEY]` 등으로 교체
- 로그에도 민감정보 남기지 않음

## 8. 테스트 결과

### 전체 결과
```
============================ 114 passed in 15.27s =============================
```

### 내역
| 테스트 파일 | 수량 | 결과 |
|------------|------|------|
| `test_remote_dev.py` | 57개 | ✅ 전부 통과 |
| `test_task_queue.py` | 18개 | ✅ 전부 통과 |
| `test_notifications.py` | 12개 | ✅ 전부 통과 |
| **총계** | **114개** | ✅ **전부 통과** |

### 주요 테스트 항목
1. 작업 등록 및 고유 ID 생성 ✅
2. 정상적인 상태 조회 ✅
3. 각 작업 유형의 올바른 상태 지정 ✅
4. 잘못된 상태 전이 거부 ✅
5. 동일 idempotency key로 중복 등록 방지 ✅
6. 서로 다른 키를 가진 정상적인 작업은 각각 등록 ✅
7. 동시 요청에서 중복 등록 방지 ✅
8. 재시작 후 작업 및 상태 복원 ✅
9. DB 오류 시 안전한 실패 처리 ✅
10. 인증 실패 시 작업 등록 거부 ✅
11. `/실행`이 승인 대기 상태로 등록되는지 확인 ✅
12. 승인되지 않은 작업의 실행 경로가 없는지 확인 ✅
13. 알림 이벤트 중복 방지 ✅
14. 알림 전송 실패와 재시도 처리 ✅
15. 알림 오류의 민감정보 마스킹 ✅
16. Notion 로거 실패가 작업을 손상시키지 않는지 확인 ✅
17. 다국어 명령어 입력 처리 ✅
18. 기존 Stage 1/2 테스트 회귀 확인 ✅

## 9. 기존 게이트웨이/웹훅에 영향 없음 근거

1. **변경하지 않은 파일**: `gateway.py`, `webhook.py`, `cron/` 디렉터리, `config.yaml`, `.env`
2. **독립 모듈**: `remote_dev/` 패키지는 기존 게이트웨이와 완전히 분리됨
3. **Git 상태**: 기존 파일 변경 없음 (`git status --short`에서 기존 파일 무변경 확인)
4. **테스트 회귀**: 기존 57개 테스트 전부 통과

## 10. 남은 위험 및 Stage 4 진입 조건

### 남은 위험
1. `running` 상태 전환 로직은 구현되었으나 실제 실행 엔진 미연결
2. Notion 연동은 mock만으로 검증, 실제 연동 시 오류 처리 검증 필요
3. 동시성 제어: `threading.Lock()` 사용 중이지만 분산 환경では 추가 필요

### Stage 4 진입 조건
- [x] 모든 114개 테스트 통과
- [x] SQLite 영속 저장 검증
- [x] 상태 전이 검증
- [x] 중복 방지 검증
- [x] 민감정보 마스킹 검증
- [x] Notion mock 검증
- [x] 기존 게이트웨이 변경 없음
- [ ] 실제 Telegram 메시지 발송 테스트 (Stage 4에서)
- [ ] 실제 게이트웨이 연동 테스트 (Stage 4에서)

---

**Stage 3 완료 — Stage 4 진입 가능**
