# 2단계 사전 기술 점검 보고서

**점검 일자:** 2026-10-11 06:30 KST  
**모드:** 읽기 전용 (변경 없음)  
**대상:** `/c/Users/Administrator/.hermes/github_workspace/telegrambot_code`

---

## A. 확인된 사실

### 1. 기본 환경
```
Python 버전: 3.15.0
Python 경로: C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\python3
가상환경:    없음
프로젝트 루트: /c/Users/Administrator/.hermes/github_workspace/telegrambot_code
```

### 2. 게이트웨이 상태
```
모델:        agnes-2.0-flash
게이트웨이:  ✓ running
플랫폼:      Telegram (@nata58AI_bot)
Cron 작업:   1개 활성 (정시 상태 보고)
```

### 3. 보안 상태
```
Git 원격:    ✅ 안전 (민감 키 없음)
로컬 설정:   ⚠️ 보존됨 (~/.continue/config.yaml, Git 미추적)
.env 파일:   ❌ 없음
```

---

## B. 기존 텔레그램 연동 구조

### 1. 현재 연동 방식
```
구성 요소:    Hermes 게이트웨이 (내장 텔레그램 클라이언트)
-bot token:  ~/.hermes/config.yaml에 저장됨
채팅 ID:      8349997580 (고정)
수신 방식:    webhook 기반 ( 게이트웨이 내부 처리)
```

### 2. 업데이트 수신 아키텍처
```
Telegram Server
      ↓ (webhook)
Hermes Gateway (포트 8080)
      ↓
내부 라우터
      ↓
에이전트 처리 ( 나타 @nata58AI)
```

### 3. 별도 회계 봇 추가 시 충돌 가능성
| 항목 | 가능성 | 설명 |
|------|--------|------|
| 토큰 충돌 | ✅ 없음 | 서로 다른 BOT_TOKEN 사용 |
| 포트 충돌 | 🟡 주의 | 게이트웨이 8080 포트 이미 사용 |
| 메시지 혼선 | 🔴 높음 | 두 봇이 같은 chat_id 수신 |
| 업데이트 충돌 | 🟡 주의 | webhook 중복 등록 가능성 |

**충돌 방지책:**
- 회계 봇은 별도 chat_id 사용 권장
- webhook 경로 분리 (`/webhook/main`, `/webhook/accounting`)
- 라우팅 로직에서 봇 토큰별 분기 처리

---

## C. Python 및 패키지 호환성

### 1. 현재 Python 환경
```
버전:    3.15.0 (최신)
호환성:  telebot, aiogram 3.x 모두 지원
권장:    3.10+ (안정성 고려 시)
```

### 2. 설치 필요 패키지
```python
# 필수
python-telegram-bot>=20.0   # 또는 aiogram>=3.0
aiosqlite>=0.19            # 비동기 SQLite

# 선택
requests>=2.31             # HTTP 클라이언트
python-dotenv>=1.0         # 환경변수 관리

# 권장 안 함 (복잡도 증가)
telebot (PyTelegramBotAPI) # 구버전, 비동기 미지원
```

### 3. 가상환경 설정 권장
```bash
# 권장 구성
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# requirements.txt 예시
python-telegram-bot==20.7
aiosqlite==0.19.0
requests==2.31.0
python-dotenv==1.0.0
```

---

## D. HTTP 429 원인과 근거

### 1. Cron 작업 정보
```
작업 ID:    3bb6a8dfbd9a
이름:       정시 상태 보고
주기:       매시간 0분 (0 * * * *)
마지막 실행: 2026-10-11 05:00:53 KST
다음 실행:   2026-10-11 06:00:00 KST
연속 실패:   9회
```

### 2. 오류 상세
```
오류 코드:  HTTP 429
메시지:     "You've reached the API rate limit for free users."
요청 ID:    20261010200049517247910mjLD83GB
발생 서비스: Agnes AI API (무료 티어)
```

### 3. 원인 분석
| 요인 | 설명 |
|------|------|
| 무료 티어 한도 | 시간당/일일 요청 수 제한 |
| 정시 보고 빈도 | 1시간 간격으로Agnes AI 호출 |
| 다중 에이전트 | 나타나 + Continue 3AI 동시 사용 |
| 재시도 과다 | 실패 시 자동 재시도로 제한 초과 |

### 4. 해결 방안 (서비스 변경 없이)

**A. 폴백 모델 설정 (권장)**
```yaml
# ~/.hermes/config.yaml
fallback:
  - provider: google
    name: gemini-2.0-flash    # 무료 티어 별도 한도
  - provider: openrouter
    name: deepseek/deepseek-r1:free  # 무료 모델
```

**B. Cron 주기 조정**
```
현재:  매시간 0분 (0 * * * *)
권장:  30분 간격 (*/30 * * * *) 또는 2시간 간격 (0 */2 * * *)
```

**C. 재시도 정책 최적화**
```python
# 최대 2회 재시도, 지수 백오프
max_retries = 2
backoff_factor = 2  # 2초, 4초 대기
```

**D. 로컬 캐싱**
- 동일한 상태 보고는 5분간 캐시하여 중복 호출 방지

---

## E. 권장 아키텍처

### 1. 단일 게이트웨이 통합 (권장)
```
┌─────────────────────────────────────────┐
│         Hermes Gateway (8080)           │
├─────────────────────────────────────────┤
│  Telegram Router                        │
│  ├─ /webhook/main (@nata58AI_bot)       │
│  └─ /webhook/accounting (@account_bot)  │
├─────────────────────────────────────────┤
│  Agent Orchestration                    │
│  ├─ 나타 (@nata58AI) - 시스템 총괄      │
│  ├─ Gemini 2.0 Flash - 메인 AI          │
│  ├─ DeepSeek R1 - failover              │
│  └─ Qwen 2.5 Coder - autocomplete       │
├─────────────────────────────────────────┤
│  Data Layer                             │
│  ├─ Notion Logger (에러 기록)           │
│  └─ SQLite (회계 데이터)                │
└─────────────────────────────────────────┘
```

### 2. 분리형 아키텍처 (대안)
```
Hermes Gateway (메인 봇)
      ↓
  Separate Accounting Bot
      ↓
  Shared SQLite Database
      ↓
  Notion Sync (읽기 전용)
```

**권장 이유:**
- 복잡한 배포 불필요
- 공통 게인웨어 관리 용이
- 단일 포인트 장애만 고려

---

## F. 안전하게 진행할 수 있는 다음 작업

### 1. 즉시 가능한 작업 (위험도: 낮음)
```
✅ 가상환경 생성 및 의존성 설치
✅ requirements.txt 작성
✅ 아키텍처 설계 문서화
✅ 회계 봇 봇토큰 발급 (Telegram @BotFather)
```

### 2. Cron 오류 해결 (위험도: 낮음)
```
✅ 폴백 모델 설정 추가
✅ Cron 주기 2시간으로 조정 검토
✅ 재시도 정책 제한 설정
```

### 3. 데이터 계층 추가 (위험도: 보통)
```
✅ SQLite 데이터베이스 파일 생성
✅ 테이블 스키마 설계
✅ Notion 동기화 로직 추가
```

### 4. 회계 봇 구현 (위험도: 높음)
```
⚠️ 게이트웨이 수정 필요
⚠️ webhook 라우팅 설정 필요
⚠️ 테스트 환경 구축 필요
```

---

## G. 위험 요소 및 주의사항

### 🔴 긴급 조치 필요
1. **Cron 지속 실패** - 9회 연속 429 오류
   - 영향: 정시 보고 불가
   - 해결: 폴백 모델 설정 또는 주기 조정

### 🟡 주의 필요
2. **포드 충돌 가능성** - 게이트웨이 8080 포트
   - 회계 봇 별도 포트 사용 권장 (8081)
3. **메시지 혼선** - 동일 chat_id 사용 시
   - 회계 봇은 별도 chat_id 사용 필수

### 🟢 정보
4. **가상환경 부재** - 의존성 관리 어려움
   - venv 생성 권장
5. **의존성 파일 부재** - 환경 재구성 어려움
   - requirements.txt 작성 권장

---

## H. 기술적 제약을 고려한 제안

### 단계 1: 기반 마련 (1-2시간)
```bash
# 1. 가상환경 생성
python -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install python-telegram-bot aiosqlite requests python-dotenv

# 3. requirements.txt 생성
pip freeze > requirements.txt
```

### 단계 2: Cron 오류 해결 (30분)
```yaml
# ~/.hermes/config.yaml 수정 (읽기 전용 확인 후)
fallback:
  - provider: google
    name: gemini-2.0-flash
cron:
  jobs:
    - schedule: "0 */2 * * *"  # 2시간 간격으로 변경 검토
```

### 단계 3: 아키텍처 구현 (2-4시간)
```
1. bot_accounting.py 생성 (독립 파일)
2. 게이트웨이 webhook 라우팅 추가
3. SQLite 데이터베이스 초기화
4. Notion 동기화 구현
```

---

**점검 완료. 다음 단계 승인 대기 중.**
