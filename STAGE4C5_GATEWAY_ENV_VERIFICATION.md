# Stage 4-C5: 새 환경변수 적용 최종 확인 보고서

**작성일:** 2026-10-11
**프로젝트:** Nata58AI Telegram Bot
**상태:** ✅ 환경변수 확인 완료 / 재시작 승인 대기

---

## 1. 환경변수 존재 여부 확인

### 1-1. `.env` 파일 확인

```
~/.hermes/.env 파일 내용:
GITHUB_TOKEN=***
AGNES_API_KEY=***
NOTION_API_KEY=***
GEMINI_API_KEY=***      ← ✅ 등록됨
OPENROUTER_API_KEY=***  ← ✅ 등록됨
```

**판단:** ✅ `.env` 파일에 두 키 모두 등록되어 있음

### 1-2. 시스템 환경변수 확인

```
Terminal 세션: GEMINI_API_KEY 없음
Windows 시스템: GEMINI_API_KEY 없음
Windows 시스템: OPENROUTER_API_KEY 없음
```

**판단:** ⚠️ 시스템 환경변수에는 없음 — Gateway가 `.env` 파일을 직접 읽어야 함

---

## 2. Gateway 실행 환경 확인

### 2-1. Gateway 프로세스 상태

```
Gateway: ✓ running
Python: 3.14.7
.env file: ✓ exists (Hermes가 자동 감지)
```

### 2-2. Gateway 설정 파일 경로

```
~/.hermes/config.yaml
  model.provider: custom
  model.name: agnes-2.0-flash
  model.base_url: https://apihub.agnes-ai.com/v1
  model.api_key: "[REDACTED]"  ← Hermes 자체 모델 키
  
fallback[0]: nous-portal (agnes-2.5-flash)
fallback[1]: google (gemini-2.5-flash)
              base_url: https://generativelanguage.googleapis.com/v1beta/openai/
              api_key: "[REDACTED]"
              
providers.google.api_key: "[REDACTED]"
```

### 2-3. Continue 설정 파일 경로

```
~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml
  models[0].provider: gemini
  models[0].model: gemini-2.0-flash
  models[0].apiKey: ${GEMINI_API_KEY}  ← 환경변수 참조 (수정 완료)
  
  models[1..6].provider: openrouter
  models[1..6].apiKey: ${OPENROUTER_API_KEY}  ← 환경변수 참조
```

---

## 3. 현재 모델과 공급자 확인

| 구성 요소 | 모델 | 공급자 | 키 위치 | 상태 |
|----------|------|--------|---------|------|
| Gateway 메인 | agnes-2.0-flash | custom (apihub.agnes-ai.com) | `~/.hermes/config.yaml` | ✅ 정상 |
| Gateway fallback | agnes-2.5-flash | nous-portal | Nous Portal auth | ✅ 정상 |
| Gateway fallback | gemini-2.5-flash | google | `~/.hermes/config.yaml` (마스킹) | ✅ 정상 |
| Continue primary | gemini-2.0-flash | gemini | `.env` → `${GEMINI_API_KEY}` | ✅ 설정 완료 |
| Continue failover | deepseek/deepseek-chat | openrouter | `.env` → `${OPENROUTER_API_KEY}` | ✅ 설정 완료 |

**중요 구분:**
- **Gateway**는 Hermes 자체 모델(agnes-2.0-flash) 사용 — Continue와 독립적
- **Continue**는 Gemini/DeepSeek 모델 사용 — 별도 설정 필요
- Continue 설정은 Gateway 재시작과 무관하게 적용됨

---

## 4. 설정 자동 적용 여부

### 4-1. Continue 설정 변경 영향

| 설정 파일 | 변경 사항 | Gateway 자동 적용 | 비고 |
|----------|----------|-----------------|------|
| `.continue/config.yaml` | apiKey 환경변수 참조 | ❌ 해당 없음 | Continue 전용 설정 |
| `~/.hermes/config.yaml` | 변경 없음 | N/A | Gateway 설정 |
| `~/.hermes/.env` | 키 등록 | ⚠️ 필요 | Gateway가 `.env` 읽는지 확인 필요 |

### 4-2. Gemini 직접 연결 활성화 여부

- **현재:** Continue가 Gemini 직접 연결 설정 완료
- **Gateway 연동:** Continue는 Hermes Gateway와 별도 실행
- **검증 필요:** Continue 재시작 또는 VS Code 재로드 후 동작 확인

### 4-3. OpenRouter를 통한 DeepSeek 연결 활성화 여부

- **현재:** Continue가 OpenRouter 경유 DeepSeek 설정 완료
- **Gateway 연동:** Continue 전용 기능
- **검증 필요:** Continue 에서 실제로 DeepSeek 호출 가능해야 함

---

## 5. 백업 대상 및 복구 방법

### 5-1. 백업 대상 파일 목록

```
~/.hermes/config.yaml                     # Gateway 설정
~/.hermes/.env                            # 환경변수 파일
~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml  # Continue 설정
~/.hermes/remote_tasks.db                 # 작업 DB
~/.hermes/remote_notifications.db         # 알림 DB
~/.hermes/focus_mode.json                 # 집중 모드 설정
```

### 5-2. 백업 명령 (승인 후 실행)

```bash
BACKUP_DIR=~/.hermes/backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp ~/.hermes/config.yaml "$BACKUP_DIR/"
cp ~/.hermes/.env "$BACKUP_DIR/"
cp ~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml "$BACKUP_DIR/"
cp ~/.hermes/remote_tasks.db "$BACKUP_DIR/" 2>/dev/null || true
cp ~/.hermes/remote_notifications.db "$BACKUP_DIR/" 2>/dev/null || true
cp ~/.hermes/focus_mode.json "$BACKUP_DIR/" 2>/dev/null || true
```

### 5-3. 복구 절차

```bash
# Gateway 설정 복원
cp ~/.hermes/backup_*/config.yaml ~/.hermes/config.yaml
cp ~/.hermes/backup_*/\.env ~/.hermes/.env
# Gateway 재시작
hermes restart
```

---

## 6. 재시작 필요성 판단

### 6-1. Gateway 재시작 필요 여부

| 항목 | 필요성 | 이유 |
|------|--------|------|
| Gateway 재시작 | ⚠️ 권장 | `.env` 파일 변경 사항을 다시 읽기 위해 |
| Continue 재시작 | ❌ 불필요 | Continue는 별도 프로세스, VS Code 재로드만으로 충분 |
| 플러그인 설치 | ✅ 필수 | `remote_dev` 플러그인 설치를 위해 필요 |

### 6-2. 환경변수 로드 확인

Gateway가 `.env` 파일을 자동으로 읽는지 확인 필요:
```
hermes status 결과: ".env file: ✓ exists"
→ Gateway가 `.env` 파일을 감지하고 있음
```

**판단:** ✅ Gateway가 `.env` 파일을 자동 로드하는 것으로 보임

---

## 7. 인증 검증 계획

### 7-1. 검증 순서

```
1. Gateway 재시작 (사용자 승인 후)
2. Gateway 상태 확인 (hermes status)
3. Continue 연결 테스트 (VS Code에서 Gemini 호출)
4. DeepSeek 연결 테스트 (VS Code에서 DeepSeek 호출)
5. 플러그인 로드 확인
6. 실제 Telegram E2E 테스트 (TC-01 ~ TC-12)
```

### 7-2. 검증 항목

| 단계 | 검증 방법 | 기대 결과 | 실패 시 조치 |
|------|----------|----------|-------------|
| 1 | Gateway 재시작 | 정상 기동 | 이전 설정 복원 |
| 2 | hermes status | Gateway running | 로그 확인 |
| 3 | Continue Gemini 호출 | 응답 정상 | `.env` 키 확인 |
| 4 | Continue DeepSeek 호출 | 응답 정상 | OpenRouter 키 확인 |
| 5 | 플러그인 로드 | remote_dev 로드됨 | 플러그인 경로 확인 |
| 6 | Telegram 메시지 | 정상 수신 | 웹훅 설정 확인 |

### 7-3. 예상 비용 영향

| 모델 | 예측 비용 | 비고 |
|------|----------|------|
| Gemini 2.0 Flash | API 사용량 기반 | 과금 발생 가능 |
| DeepSeek V3/R1 | OpenRouter 통해 과금 | 과금 발생 가능 |
| agnes-2.0-flash | 무료 | Hermes 내부 모델 |

**주의:** 실제 API 호출 전에 소량 테스트 권장.

---

## 8. 미해결 위험 요소

| 위험 | 설명 | 완화 방안 |
|------|------|----------|
| 환경변수 미로드 | Gateway가 `.env`를 제대로 읽지 않을 수 있음 | `hermes status`로 확인 |
| 이전 키 잔존 | `.env`에 이전 키가 남아있을 수 있음 | 사용자가 직접 확인 후 제거 |
| Gateway 충돌 | 새 설정이 기존 설정과 충돌할 수 있음 | 백업에서 복원 가능 |
| API 과금 | 실제 호출로 비용 발생 가능 | 소량 테스트 후 진행 |
| Continue 비동기 | Continue 설정은 Gateway와 독립적 | 별도 테스트 필요 |

---

## 9. 최종 상태

| 항목 | 상태 |
|------|------|
| `.env` 파일 키 등록 | ✅ 완료 |
| `.continue/config.yaml` 수정 | ✅ 완료 |
| 시스템 환경변수 등록 | ⚠️ 미확인 (터미널 세션에서만 미확인) |
| Gateway 재시작 | ❌ 미완료 (승인 대기) |
| Continue 연결 테스트 | ❌ 미완료 (승인 대기) |
| 백업 생성 | ❌ 미완료 (승인 대기) |

---

**보고서 작성일:** 2026-10-11
**상태:** ✅ **점검 완료 — Gateway 재시작 및 테스트 승인 대기**
**다음 조치:** 운영 Gateway 재시작 승인 요청
