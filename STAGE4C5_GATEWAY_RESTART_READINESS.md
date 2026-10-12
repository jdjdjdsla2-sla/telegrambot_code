# Stage 4-C5: Gateway 재시작 전 최종 확인 및 인증 검증 준비 보고서

**작성일:** 2026-10-11
**프로젝트:** Nata58AI Telegram Bot
**상태:** ✅ 점검 완료 / 재시작 승인 대기

---

## 1. Gateway 현재 상태

### 1-1. Gateway 프로세스 상태

```
hermes status 결과:
  Model:        agnes-2.0-flash
  Provider:     custom
  Providers:    Nous Portal, Google AI Studio, Apihub.agnes-ai.com
  Gateway:      ✓ running
  Platforms:    Telegram
  Jobs:         1 active, 1 total
```

**판단:** ✅ Gateway 정상 실행 중

### 1-2. Gateway 설정 파일

`~/.hermes/config.yaml`:
```yaml
model:
  provider: custom
  name: agnes-2.0-flash
  base_url: "https://apihub.agnes-ai.com/v1"
  api_key: "[REDACTED]"  # Hermes 자체 모델 키

fallback:
  - provider: nous-portal
    name: agnes-2.5-flash
  - provider: google
    name: gemini-2.5-flash
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
    api_key: "[REDACTED]"

providers:
  google:
    api_key: "[REDACTED]"
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"

gateway:
  enabled: true
  port: 8080
  platforms:
    telegram:
      enabled: true
      bot_token: "[REDACTED]"
      chat_id: "8349997580"
```

**판단:** ✅ Gateway 설정 정상, Hermes 자체 모델은 `apihub.agnes-ai.com` 사용

---

## 2. 환경변수 로딩 방식 확인

### 2-1. `.env` 파일 위치 및 내용

| 항목 | 값 |
|------|-----|
| 파일 경로 | `~/.hermes/.env` |
| Git 추적 | ❌ 안 됨 (안전) |
| `GEMINI_API_KEY` | ✅ 등록됨 |
| `OPENROUTER_API_KEY` | ✅ 등록됨 |

### 2-2. dotenv 사용 여부

```
grep -rn "load_dotenv" ~/.hermes/hermes-agent/
결과: 없음
```

**판단:** ⚠️ Gateway가 `.env` 파일을 자동 로드하지 않음 — 환경변수가 시스템에 설정되어 있어야 함

### 2-3. Continue 설정 로딩 방식

`.continue/config.yaml`의 `${VAR}` 치환:
- Continue는 내부적으로 환경변수 치환 지원
- `${GEMINI_API_KEY}` → `os.environ['GEMINI_API_KEY']` 참조
- `${OPENROUTER_API_KEY}` → `os.environ['OPENROUTER_API_KEY']` 참조

**판단:** ✅ Continue는 `${VAR}` 형식 지원

---

## 3. 변수 치환 지원 여부

| 설정 파일 | 치환 형식 | 지원 여부 | 비고 |
|----------|----------|----------|------|
| `.continue/config.yaml` | `${GEMINI_API_KEY}` | ✅ 지원 | Continue 내부 치환 |
| `.continue/config.yaml` | `${OPENROUTER_API_KEY}` | ✅ 지원 | OpenRouter 제공자 |
| `~/.hermes/config.yaml` | 직접 문자열 | N/A | Hermes 자체 키 |

**문제점:**
- Gateway(`~/.hermes/config.yaml`)는 `.env` 파일을 자동 로드하지 않음
- Continue는 `.env` 파일 대신 시스템 환경변수를 사용

**해결책:**
1. 시스템 환경변수에 `GEMINI_API_KEY`, `OPENROUTER_API_KEY` 설정
2. 또는 Gateway 재시작 시 `.env` 파일을 소스(source)하여 로드

---

## 4. 재시작 필요성

### 4-1. 재시작이 필요한 이유

| 이유 | 설명 |
|------|------|
| 설정 변경 반영 | `.continue/config.yaml` 수정 후 Continue 재시작 필요 |
| 환경변수 로드 | Gateway가 새 환경변수를 인식하지 못할 수 있음 |
| 플러그인 로드 | `remote_dev` 플러그인 설치 후 Gateway 재시작 필수 |

### 4-2. 재시작 전 필수 조건

- [x] `.continue/config.yaml` 수정 완료
- [x] `.env` 파일에 키 등록 확인
- [x] 환경변수 시스템 등록 필요
- [ ] Gateway 백업 생성
- [ ] 사용자 승인

---

## 5. 백업 및 복구 절차

### 5-1. 백업 대상

```bash
# 백업 디렉터리 생성
BACKUP_DIR=~/.hermes/backup_$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# 백업 파일 목록
~/.hermes/config.yaml              # Gateway 설정
~/.hermes/.env                     # 환경변수 파일
~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml  # Continue 설정
~/.hermes/remote_tasks.db          # 작업 DB
~/.hermes/remote_notifications.db  # 알림 DB
~/.hermes/focus_mode.json          # 집중 모드 설정
```

### 5-2. 복구 절차

```bash
# Gateway 재시작 실패 시
BACKUP_DIR=~/.hermes/backup_20261011_094500
cp $BACKUP_DIR/config.yaml ~/.hermes/config.yaml
cp $BACKUP_DIR/.env ~/.hermes/.env
# Gateway 재시작
hermes restart
```

---

## 6. Gemini 및 OpenRouter 인증 검증 계획

### 6-1. 검증 순서

1. **Gateway 재시작** — 수정된 설정 적용
2. **Gateway 상태 확인** — 정상 기동 확인
3. **Continue 연결 확인** — Gemini 직접 연결 테스트
4. **OpenRouter 연결 확인** — DeepSeek 모델 테스트
5. **플러그인 로드 확인** — `remote_dev` 플러그인 로드 확인
6. **E2E 테스트** — 실제 Telegram 메시지 테스트

### 6-2. 검증 항목

| 단계 | 검증 항목 | 기대 결과 | 실패 시 조치 |
|------|----------|----------|-------------|
| 1 | Gateway 기동 | 상태: running | 이전 설정으로 복원 |
| 2 | Continue 연결 | Gemini 응답 정상 | `.env` 파일 확인 |
| 3 | OpenRouter 연결 | DeepSeek 응답 정상 | API 키 확인 |
| 4 | 플러그인 로드 | `remote_dev` 로드됨 | 플러그인 경로 확인 |
| 5 | E2E 테스트 | Telegram 메시지 수신 | 웹훅 설정 확인 |

### 6-3. 예상 비용 및 사용량 영향

| 항목 | 예상 비용 | 비고 |
|------|----------|------|
| Gemini 직접 연결 | API 사용량 기반 | 과금 발생 가능 |
| OpenRouter DeepSeek | API 사용량 기반 | 과금 발생 가능 |
| Hermes 자체 모델 | 무료 | `apihub.agnes-ai.com` |
| Telegram 메시지 | 무료 | webhook 기반 |

**주의:** 실제 API 호출은 비용이 발생할 수 있으므로, 작은 텍스트로 테스트 후 진행 권장.

---

## 7. 미해결 위험 요소

| 위험 | 설명 | 완화 방안 |
|------|------|----------|
| 환경변수 미로드 | Gateway가 `.env` 파일 자동 로드 안 함 | 시스템 환경변수 설정 또는 소스 명령 사용 |
| 이전 키 잔존 | `.env` 파일에 이전 키 남아있을 수 있음 | 사용자가 직접 확인 후 제거 |
| 설정 충돌 | 새로운 설정이 기존 설정과 충돌 | 백업에서 복원 가능 |
| API 과금 | 실제 호출로 비용 발생 | 소량 테스트 후 진행 |

---

## 8. 다음 단계

### 8-1. 필요한 사용자 승인

| 번호 | 작업 | 위험도 | 필요 승인 |
|------|------|--------|----------|
| 1 | Gateway 재시작 | 낮음 | 필수 |
| 2 | Continue 연결 테스트 | 중 | 필수 |
| 3 | OpenRouter 연결 테스트 | 중 | 필수 |
| 4 | 실제 Telegram E2E 테스트 | 높음 | 필수 |

### 8-2. 승인 후 실행 순서

```
1. 백업 생성
2. Gateway 재시작
3. 상태 확인 (hermes status)
4. Gemini 연결 테스트 (소량)
5. OpenRouter 연결 테스트 (소량)
6. 플러그인 로드 확인
7. 실제 Telegram E2E 테스트 (TC-01 ~ TC-12)
```

---

## 9. 최종 상태

| 항목 | 상태 |
|------|------|
| Gateway 현재 상태 | ✅ running |
| `.continue/config.yaml` 수정 | ✅ 완료 |
| `.env` 파일 등록 | ✅ 완료 |
| 환경변수 시스템 등록 | ⚠️ 확인 필요 |
| 백업 생성 | ❌ 미완료 |
| Gateway 재시작 | ❌ 미완료 (승인 대기) |
| 인증 검증 | ❌ 미완료 (승인 대기) |

---

**보고서 작성일:** 2026-10-11
**상태:** ✅ **점검 완료 — Gateway 재시작 승인 대기**
**다음 조치:** 운영 Gateway 재시작 승인 요청
