# Notion Logger 설정 가이드
# 3AI 에러 스택 트레이스 자동 기록용

## 데이터베이스 스키마

### 테이블명: `3AI Error Log`
- `에러 ID` (Title): 고유 식별자
- `발생 시각` (Created Time): ISO 8601 형식
- `에러 타입` (Select): TypeError, AttributeError, ValueError, HTTPError, TimeoutError 등
- `HTTP 상태` (Number): 429, 500, 503 등
- `모델` (Select): gemini-2.0-flash, llama-3.3-70b, qwen-2.5-coder 등
- `프로바이더` (Select): Google, OpenRouter, Nous Portal
- `메시지` (Rich Text): 에러 상세 메시지
- `스택 트레이스` (Rich Text): 전체 에러 백트레이스
- `재생성 단계` (Number): 1-3 (재시도 횟수)
- `복구 여부` (Status): 성공/실패/대기
- `소유주 알림` (Checkbox): 경보 발송 여부
- `태그` (Multi-select): API, 코드, 설정, 네트워크

## 자동 기록 스크립트 (Python)

```python
import os
import json
import requests
from datetime import datetime
from pathlib import Path

class NotionErrorLogger:
    def __init__(self):
        self.notion_api_key = os.getenv('NOTION_API_KEY')
        self.database_id = os.getenv('NOTION_ERROR_DB_ID')
        
    def log_error(self, error_type, message, stack_trace, model='unknown', 
                  http_status=None, retry_count=1, recovery='pending'):
        """에러를 Notion 데이터베이스에 기록"""
        headers = {
            'Authorization': f'Bearer {self.notion_api_key}',
            'Content-Type': 'application/json',
            'Notion-Version': '2022-06-28'
        }
        
        payload = {
            'parent': {'database_id': self.database_id},
            'properties': {
                '에러 ID': {'title': [{'text': {'content': f'ERR-{datetime.now().strftime("%Y%m%d-%H%M%S")}'}}]},
                '발생 시각': {'date': {'start': datetime.now().isoformat()}},
                '에러 타입': {'select': {'name': error_type}},
                'HTTP 상태': {'number': http_status} if http_status else None,
                '모델': {'select': {'name': model}},
                '메시지': {'rich_text': [{'text': {'content': message}}]},
                '스택 트레이스': {'rich_text': [{'text': {'content': stack_trace[:4000]}}]},
                '재생성 단계': {'number': retry_count},
                '복구 여부': {'status': {'name': recovery}},
                '소유주 알림': {'checkbox': recovery == 'pending'},
                '태그': {'multi_select': [{'name': error_type.split('-')[0]}]}
            }
        }
        
        # None 값 제거
        payload['properties'] = {k: v for k, v in payload['properties'].items() if v is not None}
        
        response = requests.post(
            f'https://api.notion.com/v1/pages',
            headers=headers,
            json=payload
        )
        
        return response.status_code == 200
```

## 환경변수 설정 (.env)
```
NOTION_API_KEY=ntn_xxxxxxxx
NOTION_ERROR_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AQ.xxxxxxxx
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
```

## Cron 설정 (매일 09:00 KST 동기화)
```bash
# cron job 설정
0 9 * * * cd ~/.hermes/github_workspace/telegrambot_code && python notion_sync.py
```
