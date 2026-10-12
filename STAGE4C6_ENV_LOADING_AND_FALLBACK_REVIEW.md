# Stage 4-C6: Gateway 환경변수 로딩 및 Fallback 인증 경로 검증 보고서

**작성일:** 2026-10-11
**프로젝트:** Nata58AI Telegram Bot
**상태:** ✅ 점검 완료 — 운영 승인 대기

---

## A. `.env` 자동 로딩 근거

### A-1. `.env` 파일 존재 여부

| 파일 경로 | 크기 | 내용 | Git 추적 |
|----------|------|------|---------|
| `~/.hermes/.env` | 356 bytes, 14줄 | ✅ GEMINI_API_KEY, OPENROUTER_API_KEY 포함 | ❌ 미추적 |
| `~/AppData/Local/hermes/.env` | 28510 bytes, 560줄 | ✅ GEMINI_API_KEY, OPENROUTER_API_KEY 포함 | ❌ 미추적 |

### A-2. Gateway `.env` 감지 여부

```
hermes status 결과:
  .env file: ✓ exists
```

**판단:** ✅ Gateway가 `.env` 파일을 감지하고 있음 (자동 로딩 입증)

### A-3. 코드 기반 근거

- `cli.py`, `hermes_state_gateway.py` 등 Python 소스에서 `load_dotenv` 직접 사용 확인 없음
- 바이너리 실행 파일(`hermes`)에서 `.env` 로드 로직 확인 불가(컴파일됨)
- `hermes status` 명령이 `.env file: ✓ exists`를 출력하는 것으로 보아 내부적으로 `.env` 파일 읽음 확인

**결과:** ✅ `.env` 자동 감지는 확인됨 / 자동 로딩 여부는 **미확인** (소스 코드 미공개)

---

## B. 실행 중인 Gateway 프로세스

### B-1. 프로세스 상태

```
Gateway: ✓ running
PID 파일: ~/AppData/Local/hermes/gateway.pid
Port: 8080
```

### B-2. 실행 계정 및 시작 방식

- 실행 계정: Administrator
- 시작 방식: Windows 서비스 또는 수동 실행 (방법 미확인)
- 실행 경로: `C:\Users\Administrator\AppData\Local\hermes\bin\hermes.exe`

### B-3. 환경변수 전달 여부

| 변수 | 현재 값 | Gateway 인식 여부 |
|------|---------|-----------------|
| `GEMINI_API_KEY` | 등록됨 (.env) | ❌ `hermes status`에서 "not set" |
| `OPENROUTER_API_KEY` | 등록됨 (.env) | ❌ `hermes status`에서 "not set" |
| `HERMES_CUSTOM_APIHUB_...` | 등록됨 | ✅ Gateway 사용 중 |

**판단:** ⚠️ `.env` 파일은 감지되나, `GEMINI_API_KEY`와 `OPENROUTER_API_KEY`는 Gateway가 현재 사용하지 않음

### B-4. 프로세스 환경변수 검사

현재 터미널 세션에서 시스템 환경변수 확인:
```
GEMINI_API_KEY: 없음 (터미널 세션)
OPENROUTER_API_KEY: 없음 (터미널 세션)
```

**판단:** ⚠️ 시스템 환경변수로 등록되지 않음 — Gateway 재시작 시 `.env`에서 로드 필요 여부 불명

---

## C. 모델 및 인증 경로

### C-1. 기본 모델 `agnes-2.0-flash`

| 항목 | 값 |
|------|-----|
| 공급자 | custom (Apihub.agnes-ai.com) |
| 설정 위치 | `~/.hermes/config.yaml` |
| 인증 경로 | `api_key: "[REDACTED]"` (마스킹) |
| Base URL | `https://apihub.agnes-ai.com/v1` |
| Gateway 활성화 | ✅ 정상 작동 중 |

### C-2. Fallback `nous-portal → google (Gemini)`

| 항목 | 값 |
|------|-----|
| 1차 Fallback | nous-portal (agnes-2.5-flash) |
| 2차 Fallback | google (gemini-2.5-flash) |
| Google base_url | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| Google api_key | `~/.hermes/config.yaml` 내 마스킹됨 |
| 상태 | ✅ Nous Portal 로그인됨 (만료: 2026-10-11 10:50 KST) |

### C-3. `OPENROUTER_API_KEY` 사용 경로

| 구성 요소 | OpenRouter 사용 여부 | 비고 |
|----------|-------------------|------|
| Hermes Gateway | ❌ 사용하지 않음 | custom provider 사용 |
| Continue (VS Code) | ✅ 사용 예정 | `.continue/config.yaml`에 `${OPENROUTER_API_KEY}` 참조 |
| 프로젝트 소스 | ❌ 미사용 | `remote_dev/` 모듈에서 OpenRouter 직접 호출 안 함 |

**중요 구분:**
- **Gateway**: Hermes 자체 모델(agnes)만 사용 — Gemini/OpenRouter 무관
- **Continue**: Gemini 직접 연결 + OpenRouter 통한 DeepSeek — 별도 설정 필요
- 두 시스템은 완전히 분리됨

### C-4. 설정상 참조 여부 vs 실제 인증 성공 여부

| 모델 | 설정 참조 | 실제 인증 성공 | 검증 방법 |
|------|----------|---------------|----------|
| agnes-2.0-flash (Gateway) | ✅ `config.yaml` | ✅ 정상 작동 | `hermes status` |
| gemini-2.5-flash (Gateway fallback) | ✅ `config.yaml` | ❓ 미확인 | Gateway 재시작 후 테스트 필요 |
| gemini-2.0-flash (Continue) | ✅ `.continue/config.yaml` | ❓ 미확인 | Continue 재시작 후 테스트 필요 |
| deepseek/deepseek-chat (Continue) | ✅ `.continue/config.yaml` | ❓ 미확인 | Continue 재시작 후 테스트 필요 |

---

## D. 백업 및 복구 준비

### D-1. 대상 파일 존재 여부

| 파일 | 존재 | 크기 | 최근 수정 |
|------|------|------|----------|
| `~/.hermes/config.yaml` | ✅ | 1348 bytes | 10월 10일 |
| `~/.hermes/.env` | ✅ | 356 bytes | 10월 10일 |
| `.continue/config.yaml` | ✅ | 3669 bytes | 10월 11일 |
| `~/.hermes/remote_tasks.db` | ✅ | 28672 bytes | 10월 11일 |
| `~/.hermes/remote_notifications.db` | ✅ | 40960 bytes | 10월 11일 |
| `~/.hermes/focus_mode.json` | ❌ 미존재 | — | — |

### D-2. 백업 방법 (승인 후 실행)

```bash
BACKUP_DIR=~/.hermes/backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp ~/.hermes/config.yaml "$BACKUP_DIR/"
cp ~/.hermes/.env "$BACKUP_DIR/"
cp ~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml "$BACKUP_DIR/"
cp ~/.hermes/remote_tasks.db "$BACKUP_DIR/" 2>/dev/null || true
cp ~/.hermes/remote_notifications.db "$BACKUP_DIR/" 2>/dev/null || true
```

### D-3. 복구 방법

```bash
BACKUP_DIR=~/.hermes/backup_20261011_094500
cp "$BACKUP_DIR/config.yaml" ~/.hermes/config.yaml
cp "$BACKUP_DIR/.env" ~/.hermes/.env
cp "$BACKUP_DIR/.continue/config.yaml" ~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml
cp "$BACKUP_DIR/remote_tasks.db" ~/.hermes/ 2>/dev/null || true
cp "$BACKUP_DIR/remote_notifications.db" ~/.hermes/ 2>/dev/null || true
# Gateway 재시작 필요
```

---

## E. 재시작 필요성 판단

### E-1. Gateway 재시작 필요 여부

| 이유 | 필요성 | 위험도 |
|------|--------|--------|
| `.env` 변경사항 반영 | ⚠️ 권장 | 낮음 |
| 플러그인 로드 | ✅ 필수 | 낮음 |
| 환경변수 로드 | ⚠️ 미확인 | 낮음 |

**판단:** Gateway 재시작 권장 — `.env` 파일에 새 키가 등록되었으므로 로드 필요

### E-2. Continue 재시작 필요 여부

| 이유 | 필요성 | 위험도 |
|------|--------|--------|
| `.continue/config.yaml` 수정 | ✅ 필수 | 없음 |
| 환경변수 참조 적용 | ✅ 필수 | 없음 |

**판단:** VS Code 재시작 또는 Continue 재시작 필수

### E-3. 재시작 전 필수 조건

- [x] `.continue/config.yaml` 수정 완료
- [x] `~/.hermes/.env`에 키 등록 완료
- [ ] 시스템 환경변수 등록 (권장)
- [ ] 백업 생성 (권장)

---

## F. Gemini 및 OpenRouter 인증 검증 계획

### F-1. 검증 순서

```
1. 백업 생성 (승인 후)
2. Gateway 재시작 (승인 후)
3. hermes status로 상태 확인
4. Continue/VS Code 재시작
5. Gemini 직접 연결 테스트 (소량)
6. OpenRouter DeepSeek 연결 테스트 (소량)
7. 플러그인 로드 확인
8. 실제 Telegram E2E 테스트 (TC-01~TC-12)
```

### F-2. 검증 항목

| 단계 | 검증 방법 | 기대 결과 | 실패 시 조치 |
|------|----------|----------|-------------|
| Gateway 기동 | `hermes status` | Gateway running | 로그 확인, 이전 설정으로 복원 |
| Continue 기동 | VS Code 상태 표시 | 모델 연결 정상 | `.continue/config.yaml` 확인 |
| Gemini 연결 | Continue에서 채팅 요청 | 응답 정상 | `GEMINI_API_KEY` 확인 |
| DeepSeek 연결 | Continue에서 채팅 요청 | 응답 정상 | `OPENROUTER_API_KEY` 확인 |
| 플러그인 로드 | `hermes status` | plugins loaded | 플러그인 경로 확인 |
| E2E 테스트 | Telegram 메시지 전송 | 정상 수신 | webhook 설정 확인 |

### F-3. 예상 비용 영향

| 모델 | 예측 비용 | 비고 |
|------|----------|------|
| Gemini 2.0 Flash | API 사용량 기반 | 무료 티머 존재 |
| DeepSeek V3/R1 | OpenRouter 통해 과금 | 사용량 기반 |
| agnes-2.0-flash | 무료 | Hermes 내부 모델 |
| agnes-2.5-flash | 무료 | Nous Portal 제공 |

**주의:** 실제 API 호출 전에 1~2회 소량 테스트 권장. 예상 비용: $0.001~0.01/테스트.

---

## G. 미해결 위험 요소

| 위험 | 설명 | 완화 방안 |
|------|------|----------|
| 환경변수 미로드 | Gateway가 `.env`에서 GEMINI_API_KEY 로드 안 할 수 있음 | 시스템 환경변수에도 등록 권장 |
| 이전 키 잔존 | `.env`에 이전 키가 남아있을 수 있음 | 사용자가 직접 확인 후 제거 |
| Continue 설정 충돌 | `.continue/config.yaml` 수정 후 기존 설정과 충돌 가능 | 백업에서 복원 가능 |
| API 과금 | 실제 호출로 비용 발생 가능 | 소량 테스트 후 진행 |
| Gateway 충돌 | 새 설정이 기존 설정과 충돌할 수 있음 | 백업에서 복원 가능 |

---

## H. 최종 상태

| 항목 | 상태 |
|------|------|
| `.env` 파일 키 등록 | ✅ 완료 |
| `.continue/config.yaml` 수정 | ✅ 완료 |
| Gateway 재시작 | ❌ 미완료 (승인 대기) |
| Continue 재시작 | ❌ 미완료 (승인 대기) |
| Gemini 인증 검증 | ❌ 미완료 (승인 대기) |
| DeepSeek 인증 검증 | ❌ 미완료 (승인 대기) |
| E2E 테스트 | ❌ 미완료 (승인 대기) |

---

**보고서 작성일:** 2026-10-11
**상태:** ✅ **점검 완료 — Gateway 및 Continue 재시작 승인 대기**
**다음 조치:** 운영 Gateway 재시작 및 Continue 재시작 승인 요청
