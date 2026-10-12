# Stage 4-C3: Telegram E2E 통합 테스트 계획서

**작성일:** 2026-10-11
**프로젝트:** Nata58AI Telegram Bot
**상태:** 계획 작성 중 / 실행 대기
**참고:** STAGE4C2FINAL_INTEGRATION_REPORT.md

---

## 1. 현재 상태 확인

### Git 상태
```
현재 브랜치: main
최신 커밋: 100dec6 feat: add VS Code settings for Continue 3AI autocomplete

변경 파일 (미커밋):
M  remote_dev/router.py          - 집중 모드 핸들러 추가, 중국어→한국어 번역
M  remote_dev/notifications.py   - Focus Mode 연동 (should_suppress 체크)
M  remote_dev/command_parser.py  - 알림상태, 집중모드 명령어 등록
M  remote_dev/task_queue.py      - approve_task 중복 방지 로직
M  tests/test_notifications.py   - Focus Mode 싱글턴 초기화 추가
M  tests/test_task_queue.py      - Focus Mode 싱글턴 초기화 추가
M  tests/test_router.py          - 명령어 핸들러 맵 검증 업데이트
M  tests/test_remote_dev.py      - 허용 명령어 수 업데이트 (10→12)
A  remote_dev/focus_mode.py      - 신규: 집중 모드 관리 모듈
A  tests/test_focus_mode.py      - 신규: Focus Mode 테스트 (13개)
D  .continue/config.yaml         - staged로 삭제됨 (API 키 포함)
```

### 테스트 실행 결과
```
======================= 183 passed, 1 warning in 17.02s =======================
```

### 신규 13개 테스트 상세
| 테스트 클래스 | 테스트명 | 검증 항목 |
|--------------|----------|----------|
| TestFocusModeBasic | test_default_disabled | 기본 상태 비활성화 |
| TestFocusModeBasic | test_enable_and_disable | 켜기/끄기 기능 |
| TestFocusModeBasic | test_toggle | 토글 기능 |
| TestFocusModeBasic | test_persistence | 파일 영속성 |
| TestFocusModeBasic | test_suppress_logic | 억제 논리 (긴급/일반 구분) |
| TestFocusModeNotifications | test_emission_without_focus_mode | 집중 모드OFF 시 모든 전송 |
| TestFocusModeNotifications | test_emission_with_focus_mode_enabled | 집중 모드ON 시 일반 억제, 긴급 전송 |
| TestFocusModeNotifications | test_suppressed_count_tracking | 억제 카운트 추적 |
| TestFocusModeNotifications | test_critical_alerts_not_suppressed | 긴급 알림 항상 전송 |
| TestFocusModeRouterCommands | test_notification_status_command | /알림상태 핸들러 |
| TestFocusModeRouterCommands | test_focus_mode_commands | /집중모드 켜기/끄기 핸들러 |
| TestFocusModeEdgeCases | test_reset | 초기화 기능 |
| TestFocusModeEdgeCases | test_large_suppressed_log | 100개 제한 검증 |

### 미검증 항목 (로컬 테스트로 확인 불가)
- 실제 Telegram 웹훅 수신
- 실제 버튼 콜백 처리
- 실제 사용자 인증 흐름
- 실제 DB 파일 생성 및 호환성
- Gateway 플러그인 자동 로딩

---

## 2. API 키 및 Git 보안 점검

### 민감정보 탐지 결과
| 파일 | 위치 | 상태 | 비고 |
|------|------|------|------|
| `.continue/config.yaml` | 라인 8, 39, 53 | ✅ 마스킹됨 | `***` 표시 |
| `.continue/config.yaml` | 라인 13, 18, 24, 29, 34, 67 | ✅ 환경변수 | `${OPEN...KEY}` |
| `auto_purge_rebuild.py` | 여러 줄 | ✅ 마스킹됨 | `***` 또는 `${VAR}` |
| `notion_logger.py` | 라인 23 | ✅ 안전 | `os.getenv('NOTION_API_KEY')` |
| `tests/*.py` | 여러 곳 | ✅ 안전 | 더미 데이터만 사용 |
| `remote_dev/*.py` | 여러 곳 | ✅ 안전 | 환경변수 참조만 |

### Git 이력 검사
| 확인 항목 | 결과 | 비고 |
|-----------|------|------|
| 현재 커밋에 민감정보 포함 여부 | ✅ 없음 | 최신 커밋은 설정 파일 제거 |
| 과거 커밋에 민감정보 포함 가능성 | ⚠️ 미확인 | `01ee177` 이후 마스킹으로 전환됨 |
| 원격 저장소 푸시 여부 | ❌ 미푸시 | 로컬 저장소에만 존재 |
| `.gitignore`에 민감 파일 등록 | ⚠️ 부분적 | `.continue/config.yaml`만 등록, `venv/`, `*.db` 누락 |

### API 키 폐기 상태
- **확인 방법**: Gemini Console, OpenRouter 대시보드 직접 접근 필요
- **현재 상태**: 미확인 (서비스 화면 접근 불가)
- **권장 조치**: 사용자가 다음 경로에서 이전 키 확인 및 폐기
  - Gemini: https://aistudio.google.com/app/apikey
  - OpenRouter: https://openrouter.ai/keys

### Git 보안 권고사항
1. `.gitignore`에 다음 항목 추가 권장:
   ```
   venv/
   __pycache__/
   *.db
   *.json
   *.log
   ```
2. `auto_purge_rebuild.py`의 `apiKey: "***"` 는 마스킹되어 안전하나, 실제 값이 존재할 경우 삭제 권장
3. GitHub 푸시 전 `.git log --all --oneline`으로 이전 커밋 재확인 권장

---

## 3. Telegram 통합 테스트 계획

### 테스트 환경 사전 조건
- Gateway 재시작 완료 ( 별도 승인 필요 )
- 플러그인 디렉터리 설치: `~/.hermes/hermes-agent/plugins/remote_dev/`
- 봇 토큰 설정 확인 (`TELEGRAM_BOT_TOKEN` 환경변수)
- 개인 채팅 ID 확인 (운영자 본인)

### 테스트 케이스 목록

#### TC-01: 승인된 비공개 채팅에서의 기본 명령 처리
- **사전 조건**: 인증된 사용자, 개인 채팅
- **절차**: `/상태` → `/도움말` 메시지 전송
- **기대 결과**: 시스템 상태 메시지, 명령어 목록 반환
- **실패 시 중단 조건**: 메시지 미수신 또는 인증 오류 메시지 수신

#### TC-02: 비인가 사용자 접근 거부
- **사전 조건**: 비인가 user_id (예: 999999), 개인 채팅
- **절차**: `/상태` 메시지 전송
- **기대 결과**: "인증되지 않은 사용자입니다" 또는 "인증 차단됨" 메시지
- **실패 시 중단 조건**: 명령이 성공적으로 처리됨

#### TC-03: 그룹 채팅 메시지 차단
- **사전 조건**: 인증된 사용자, 그룹 chat_type='group'
- **절차**: `/상태` 메시지 전송
- **기대 결과**: 스킵 (응답 없음), 로그에 "rejected from group chat" 기록
- **실패 시 중단 조건**: 그룹에서 응답 메시지 수신

#### TC-04: 조사 작업 등록 및 상태 확인
- **사전 조건**: 인증된 사용자, 개인 채팅
- **절차**: `/조사 프로젝트 분석` → `/작업 <task_id>`
- **기대 결과**: 조사 작업 QUEUED 상태, 작업 ID 반환
- **실패 시 중단 조건**: 작업 미등록 또는 상태 오류

#### TC-05: 실행 요청 후 승인 대기
- **사전 조건**: 인증된 사용자, 개인 채팅
- **절차**: `/실행 파일 생성 스크립트 작성` → `/작업 <task_id>`
- **기대 결과**: 작업 WAITING_APPROVAL 상태로 등록, 승인 대기 메시지
- **실패 시 중단 조건**: RUNNING 상태로 전이 또는 미등록

#### TC-06: 승인, 거절, 취소 처리
- **사전 조건**: TC-05 완료 (승인 대기 작업 존재)
- **절차**: 
  1. `/승인 <task_id>` → 상태 RUNNING 확인
  2. 새 작업 생성 후 `/거절 <task_id> 사유` → 상태 FAILED 확인
  3. 새 작업 생성 후 `/취소 <task_id>` → 상태 CANCELLED 확인
- **기대 결과**: 각 명령마다 올바른 상태 전이 및 메시지 반환
- **실패 시 중단 조건**: 잘못된 상태 전이 또는 권한 오류 메시지 없음

#### TC-07: 중복 승인 차단
- **사전 조건**: TC-05 완료 (승인 대기 작업)
- **절차**: `/승인 <task_id>` 두 번 연속 실행
- **기대 결과**: 두 번째는 "이미 처리된 요청입니다" 메시지
- **실패 시 중단 조건**: 두 번째 승인 성공 또는 상태 두 번 변경

#### TC-08: 집중 모드 켜기/끄기/요약
- **사전 조건**: 인증된 사용자, 개인 채팅
- **절차**: 
  1. `/집중모드 켜기` → 활성화 확인
  2. `/알림상태` → 활성화 상태 확인
  3. `/집중모드 끄기` → 비활성화 확인
  4. `/집중모드 요약` → 억제된 알림 목록 확인
- **기대 결과**: 각 명령마다 올바른 상태 반환
- **실패 시 중단 조건**: 상태 변경 실패 또는 잘못된 메시지 반환

#### TC-09: 집중 모드 알림 필터링
- **사전 조건**: 집중 모드 활성화
- **절차**: 시스템 이벤트를 트리거하여 시작/완료 알림이 억제되고, 승인/실패 알림이 전송되는지 확인
- **기대 결과**: 일반 알림 suppression_log에 기록, 긴급 알림은 전송
- **실패 시 중단 조건**: 긴급 알림 억제 또는 일반 알림 전송

#### TC-10: 승인 후 실행 계획 변경 거부
- **사전 조건**: 승인된 작업 (RUNNING)
- **절차**: 작업 설명을 변경한 후 재승인 시도
- **기대 결과**: 변경 감지 또는 기존 승인 무효화 (구현 필요 시)
- **실패 시 중단 조건**: 변경 감지 없이 실행 또는 승인 실패

#### TC-11: 오류 발생 시 안전한 실패
- **사전 조건**: DB 연결 오류 시뮬레이션 또는 서비스 오류
- **절차**: 고의적 오류 트리거 (조건부)
- **기대 결과**: 시스템이 크래시되지 않고 안정적인 오류 메시지 반환
- **실패 시 중단 조건**: Gateway 크래시 또는 미처리 예외 로그

#### TC-12: 민감정보 마스킹 검증
- **사전 조건**: 민감정보 포함 작업 설명으로 `/실행 api_key=sk-or-xxx token=ABC123`
- **절차**: 작업 등록 후 `/상세 <task_id>` 조회
- **기대 결과**: API 키 패턴이 `[API_KEY]`, `[BOT_TOKEN]` 등으로 마스킹됨
- **실패 시 중단 조건**: 원본 민감정보가 메시지에 노출됨

---

## 4. 자동 테스트 vs 실제 Telegram 테스트 구분

| 항목 | 자동 테스트 | 실제 Telegram 테스트 |
|------|------------|---------------------|
| 명령어 파싱 | ✅ 검증됨 | 미실시 |
| 상태 전이 로직 | ✅ 검증됨 | 미실시 |
| 승인/거절/취소 흐름 | ✅ 검증됨 | 미실시 |
| 중복 승인 방지 | ✅ 검증됨 | 미실시 |
| 민감정보 마스킹 | ✅ 검증됨 | 미실시 |
| Focus Mode 필터링 | ✅ 검증됨 | 미실시 |
| 실제 Telegram 웹훅 수신 | ❌ 미검증 | 필수 검증 |
| 실제 버튼 콜백 | ❌ 미검증 | 필수 검증 |
| 실제 인증 흐름 | ⚠️ 부분 검증 | 필수 검증 |
| 실제 DB 파일 생성 | ⚠️ 임시 DB 사용 | 필수 검증 |
| Gateway 플러그인 로드 | ❌ 미검증 | 필수 검증 |

---

## 5. 보안 위험 및 해결되지 않은 항목

### 발견된 보안 위험
1. **버전 해시 미구현**: 승인 후 작업 계획 변경 감지 없음 → 오케스트레이터 연동 시 필요
2. **다중 작업 종료 미감지**: Focus Mode 자동 해제 로직 미구현
3. **`.gitignore` 누락**: `venv/`, `*.db`, `*.json` 미포함

### 해결 필요 사항
1. GitHub 푸시 전 `.gitignore` 업데이트 필요
2. 이전 API 키 폐기 확인 필요 (사용자 직접 확인)
3. 실제 Telegram 테스트를 위한 Gateway 재시작 승인 필요

### 위험 수준
| 항목 | 위험도 | 영향 범위 |
|------|--------|----------|
| 이전 API 키 활성화 | 높음 | API 과금, 보안 위협 |
| 플러그인 배포 전 미검증 | 중간 | 운영 환경 불안정 |
| Git 민감정보 누출 가능성 | 낮음 | 커밋 이력 확인 필요 |

---

## 6. Gateway 플러그인 등록 경로 확인

### 공식 플러그인 등록 경로
- Gateway 플러그인 디렉터리: `~/.hermes/hermes-agent/plugins/`
- 각 플러그인은 `__init__.py` 파일 필요
- `register(ctx)` 함수 필수 정의

### 현재 구현 상태
- `remote_dev/plugin.py`: `register(ctx)` 규약 준수 ✅
- `pre_gateway_dispatch_handler`: async 함수로 정의됨 ✅
- `COMMAND_HANDLER_MAP`: 12개 명령 매핑 완료 ✅

### 설치 예상 경로
```
~/.hermes/hermes-agent/plugins/remote_dev/
├── __init__.py          (plugin.py 내용과 동일하게 구성)
├── plugin.py            (gateway 플러그인 어댑터)
├── router.py            (명령 라우터)
├── task_queue.py        (작업 대기열)
├── auth.py              (인증 관리자)
├── notifications.py     (알림 서비스)
├── focus_mode.py        (집중 모드)
└── command_parser.py    (명령 파서)
```

---

## 7. 실행 계획 요약

### 단계별 실행 순서
1. **Gateway 재시작** (승인 필요)
2. **플러그인 설치** (승인 필요)
3. **기본 명령 테스트** (TC-01 ~ TC-03)
4. **작업 관리 테스트** (TC-04 ~ TC-07)
5. **Focus Mode 테스트** (TC-08 ~ TC-09)
6. **보안 테스트** (TC-10 ~ TC-12)
7. **결과 기록 및 보고**

### 중단 조건 (All-or-Nothing)
다음 중 하나라도 발생 시 전체 테스트 중단:
- Gateway 크래시 또는 재시작 필요
- 인증 시스템 오류 (모든 사용자 차단)
- 민감정보 노출 확인
- DB 손상 또는 데이터 손실

### 재시작 계획
중단 발생 시:
1. Gateway 재시작
2. 플러그인 재설치
3. 테스트从头执行 (첫 번째부터)

---

## 8. 승인 요청 사항

다음 작업을 실행하기 위해 승인이 필요합니다:

1. **운영 Gateway 재시작**
2. **플러그인 디렉터리 생성 및 파일 복사**
3. **실제 Telegram 통합 테스트 실행**
4. **테스트 결과 기록 및 보고**

---

**보고서 작성일:** 2026-10-11
**상태:** 계획 작성 완료, 실행 대기
**다음 조치:** stage_4D_실제_Telegram_통합테스트_승인_요청
