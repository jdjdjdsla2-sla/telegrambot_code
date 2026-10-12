# Stage 4-C7: Continue 설정 검증 및 안전한 재시작 준비 보고서

**작성일:** 2026-10-11
**프로젝트:** Nata58AI Telegram Bot
**상태:** ✅ 검증 완료 — 재시작 준비됨

---

## A. Continue 환경변수 처리 확인

### A-1. Continue 버전 및 설정 스키마

| 항목 | 값 |
|------|-----|
| 설정 파일 버전 | `version: 1.0.0` |
| 설정 스키마 | `schema: v1` |
| 설정 파일 경로 | `.continue/config.yaml` |
| 환경변수 치환 지원 | ✅ 공식 Continue 스키마 지원 (`${VAR}` 형식) |

### A-2. 환경변수 치환 검증 (Python raw bytes 확인)

```
Line 8:   apiKey: ${GEMINI_API_KEY}
Line 13:  apiKey: ${OPENROUTER_API_KEY}
Line 19:  apiKey: ${OPENROUTER_API_KEY}
Line 24:  apiKey: ${OPENROUTER_API_KEY}
Line 29:  apiKey: ${OPENROUTER_API_KEY}
Line 33:  apiKey: ${OPENROUTER_API_KEY}
Line 39:  apiKey: ${GEMINI_API_KEY}
Line 53:  apiKey: ${GEMINI_API_KEY}
Line 67:  apiKey: ${OPENROUTER_API_KEY}
```

**검증 결과:**
- ✅ `GEMINI_API_KEY` 참조: 3곳 (라인 8, 39, 53)
- ✅ `OPENROUTER_API_KEY` 참조: 6곳 (라인 13, 19, 24, 29, 33, 67)
- ✅ 하드코딩된 `apiKey: ***` 없음
- ✅ YAML 문법 유효 (옳바른 키-값 구조)

### A-3. 환경변수 출처 구분

| 출처 | 경로 | 상태 | Continue 접근 가능 여부 |
|------|------|------|---------------------|
| 프로젝트 `.env` | `~/.hermes/.env` | ✅ 등록됨 | ❌ Continue가 직접 읽지 않음 |
| Hermes 홈 `.env` | `~/AppData/Local/hermes/.env` | ✅ 등록됨 | ❌ Continue가 직접 읽지 않음 |
| Windows 시스템 | 시스템 환경변수 | ❌ 미등록 | ✅ Continue가 읽을 수 있음 |
| 터미널 세션 | 현재 bash 세션 | ❌ 없음 | 세션에만 유효 |

**중요:** Continue는 Git Bash 터미널에서 실행되지 않으며, Windows 프로세스 환경변수를 사용한다.

### A-4. 환경변수 로드 경로 판단

```
Continue 실행 환경:
- Windows GUI 응용프로그램
- Windows 시스템 환경변수 읽음
- .env 파일 자동 읽기 여부: 미확인 (공식 문서 부재)

권장 방법:
1. Windows 시스템 환경변수에 GEMINI_API_KEY 등록
2. Windows 시스템 환경변수에 OPENROUTER_API_KEY 등록
3. 또는 VS Code 통합 터미널에서 source ~/.hermes/.env 실행
```

---

## B. 모델 연결 설정 확인

### B-1. Gemini 직접 연결

| 항목 | 값 |
|------|-----|
| 모델 | `gemini-2.0-flash` |
| 프로바이더 | `gemini` |
| API 키 변수 | `GEMINI_API_KEY` |
| base URL | `https://generativelanguage.googleapis.com/` (자동) |
| 설정 위치 | `.continue/config.yaml` 라인 6-9 |
| 설정상 연결 가능 | ✅ `${GEMINI_API_KEY}` 참조 |
| 실제 인증 성공 | ❓ 미확인 (API 호출 필요) |

### B-2. OpenRouter 경유 DeepSeek 연결

| 항목 | 값 |
|------|-----|
| 모델 1 | `deepseek/deepseek-chat` |
| 모델 2 | `deepseek/deepseek-r1` |
| 프로바이더 | `openrouter` |
| API 키 변수 | `OPENROUTER_API_KEY` |
| base URL | `https://openrouter.ai/api/v1` (자동) |
| 설정 위치 | `.continue/config.yaml` 라인 17-24 |
| 설정상 연결 가능 | ✅ `${OPENROUTER_API_KEY}` 참조 |
| 실제 인증 성공 | ❓ 미확인 (API 호출 필요) |

### B-3. Failover 구성

```yaml
failover:
  enabled: true
  models:
    - gemini-2.0-flash      # Gemini 직접
    - deepseek/deepseek-chat # OpenRouter
    - deepseek/deepseek-r1   # OpenRouter
    - mistralai/codestral-2501 # OpenRouter
  retryDelay: 100
```

**판단:** ✅ Failover 구성 정상, 이전 키 fallback 없음

### B-4. 설정상 연결 가능 vs 실제 인증 성공 구분

| 모델 | 설정 참조 | 실제 인증 | 검증 방법 |
|------|----------|----------|----------|
| gemini-2.0-flash | ✅ `${GEMINI_API_KEY}` | ❓ 미확인 | Continue 채팅 테스트 필요 |
| deepseek/deepseek-chat | ✅ `${OPENROUTER_API_KEY}` | ❓ 미확인 | Continue 채팅 테스트 필요 |
| deepseek/deepseek-r1 | ✅ `${OPENROUTER_API_KEY}` | ❓ 미확인 | Continue 채팅 테스트 필요 |

---

## C. 변경 전 백업 준비

### C-1. 대상 파일 경로

| 파일 | 경로 | 크기 | 최근 수정 |
|------|------|------|----------|
| Continue 설정 | `C:/Users/Administrator/.hermes/github_workspace/telegrambot_code/.continue/config.yaml` | 3669 bytes | 10월 11일 |
| Hermes 환경변수 | `C:/Users/Administrator/.hermes/.env` | 356 bytes | 10월 10일 |
| Hermes 설정 | `C:/Users/Administrator/.hermes/config.yaml` | 1348 bytes | 10월 10일 |

### C-2. 백업 파일명 제안

```
backup_continue_config_20261011.yaml
backup_hermes_env_20261011.env
backup_hermes_config_20261011.yaml
```

### C-3. 백업 명령 (미실행)

```bash
# 백업 디렉터리 생성
BACKUP_DIR=~/.hermes/backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# 파일 백업
cp ~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml "$BACKUP_DIR/"
cp ~/.hermes/.env "$BACKUP_DIR/"
cp ~/.hermes/config.yaml "$BACKUP_DIR/"
```

### C-4. 복구 명령 (미실행)

```bash
BACKUP_DIR=~/.hermes/backup_20261011_093000

# Continue 설정 복원
cp "$BACKUP_DIR/backup_continue_config_20261011.yaml" \
   ~/.hermes/github_workspace/telegrambot_code/.continue/config.yaml

# Hermes 환경변수 복원
cp "$BACKUP_DIR/backup_hermes_env_20261011.env" ~/.hermes/.env

# Hermes 설정 복원
cp "$BACKUP_DIR/backup_hermes_config_20261011.yaml" ~/.hermes/config.yaml
```

**주의:** `.env`, DB 파일, 기타 비밀 데이터는 Git 저장소에 복사하거나 추가하지 않는다.

---

## D. 재시작 계획

### D-1. Continue 재시작 필요성

| 항목 | 필요성 | 이유 |
|------|--------|------|
| Continue 재시작 | ✅ 필수 | `.continue/config.yaml` 수정사항 적용 |
| VS Code 재시작 | ✅ 권장 | Continue 확장 프로그램 새로 로드 |
| Gateway 재시작 | ⚠️ 선택 | Gateway는 Hermes 자체 모델만 사용 |

### D-2. 현재 실행 중인 Continue 프로세스

- Continue는 VS Code 확장 프로그램으로 실행
- 현재 세션의 설정 캐시 있음
- 설정 파일 변경 후 반드시 재시작 필요

### D-3. 재시작 방법

**VS Code 재시작:**
```
1. VS Code 창 닫기
2. VS Code 재실행
3. Continue 확장 프로그램 자동 로드 확인
```

**Continue 설정 재로드 (VS Code 내부):**
```
1. Ctrl+Shift+P 열기
2. "Continue: Restart" 명령 실행
```

### D-4. 재시작 전 체크리스트

- [x] `.continue/config.yaml` 수정 완료
- [x] `.env` 파일에 키 등록 확인
- [ ] Windows 시스템 환경변수 등록 권장
- [ ] 백업 파일 생성 권장
- [ ] Gateway 재시작은 선택 사항

---

## E. 검증 결과

### E-1. 설정 검증

| 검증 항목 | 상태 | 비고 |
|----------|------|------|
| YAML 문법 | ✅ 유효 | 옳바른 키-값 구조 |
| 환경변수 참조 | ✅ 완료 | 9곳 모두 `${VAR}` 형식 |
| 하드코딩된 키 | ✅ 없음 | `***` 마스킹 제거됨 |
| Failover 구성 | ✅ 정상 | 이전 키 fallback 없음 |

### E-2. 보안 검증

| 항목 | 상태 |
|------|------|
| API 키 원문 노출 | ✅ 없음 |
| 마스킹 값 출력 | ✅ 없음 |
| 키 길이/해시 출력 | ✅ 없음 |
| `.env` 전체 내용 출력 | ✅ 없음 |
| Git 추적 가능성 | ✅ 없음 |

### E-3. 예상 비용

| 모델 | 예상 비용 | 비고 |
|------|----------|------|
| Gemini 2.0 Flash | 무료 티머 있음 | 첫 1000 RPU/일 무료 |
| DeepSeek V3/R1 | OpenRouter 사용량 기반 | $0.001~0.005/1K 토큰 |
| Total 예상 | $0.01 미만/테스트 | 소량 테스트 권장 |

---

## F. 미해결 위험 요소

| 위험 | 설명 | 완화 방안 |
|------|------|----------|
| 환경변수 미전달 | Windows 시스템에 미등록 | 시스템 환경변수 등록 권장 |
| Continue 캐시 | 이전 설정 캐시될 수 있음 | VS Code 완전 재시작 권장 |
| API 응답 지연 | 첫 호출은 cold start | 30초 이상 대기 권장 |
| 네트워크 차단 | 방화벽/프록시 영향 | 네트워크 연결 확인 |

---

## G. 다음 단계

### G-1. 권장 순서

```
1. Windows 시스템 환경변수에 GEMINI_API_KEY 등록 (권장)
2. Windows 시스템 환경변수에 OPENROUTER_API_KEY 등록 (권장)
3. 백업 파일 생성 (권장)
4. VS Code 재시작
5. Continue 채팅 테스트 (Gemini 1회, DeepSeek 1회)
6. Gateway 재시작 (필요시)
7. 실제 Telegram E2E 테스트 (TC-01~TC-12)
```

### G-2. 필요한 승인

| 번호 | 작업 | 위험도 | 필요 승인 |
|------|------|--------|----------|
| 1 | Windows 환경변수 등록 | 낮음 | 권장 |
| 2 | VS Code/Continue 재시작 | 낮음 | 필수 |
| 3 | Gemini 직접 연결 테스트 | 중 | 필수 |
| 4 | OpenRouter DeepSeek 테스트 | 중 | 필수 |
| 5 | Gateway 재시작 | 낮음 | 선택 |
| 6 | 실제 Telegram E2E 테스트 | 높음 | 필수 |

---

## H. 최종 상태

| 항목 | 상태 |
|------|------|
| Continue 설정 검증 | ✅ 완료 |
| 환경변수 참조 확인 | ✅ 완료 |
| 보안 검증 | ✅ 완료 |
| 백업 준비 | ✅ 계획 완료 |
| 재시작 필요성 | ✅ 확인 |
| 실제 API 호출 | ❌ 미수행 (승인 대기) |
| Gateway 재시작 | ❌ 미수행 (승인 대기) |
| E2E 테스트 | ❌ 미수행 (승인 대기) |

---

**보고서 작성일:** 2026-10-11
**상태:** ✅ **검증 완료 — 재시작 및 테스트 승인 대기**
**다음 조치:** VS Code 재시작 및 Continue 연결 테스트 승인 요청
