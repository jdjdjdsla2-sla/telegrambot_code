#!/usr/bin/env python3
"""
Notion Error Logger
에러 스택 트레이스를 Notion 데이터베이스에 자동 기록
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path

class NotionErrorLogger:
    def __init__(self):
        self.notion_api_key = os.getenv('NOTION_API_KEY')
        self.database_id = os.getenv('NOTION_ERROR_DB_ID')
        
        if not self.notion_api_key:
            raise ValueError("NOTION_API_KEY environment variable not set")
        if not self.database_id:
            raise ValueError("NOTION_ERROR_DB_ID environment variable not set")
    
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
                '모델': {'select': {'name': model}},
                '메시지': {'rich_text': [{'text': {'content': message}}]},
                '스택 트레이스': {'rich_text': [{'text': {'content': stack_trace[:4000]}}]},
                '재생성 단계': {'number': retry_count},
                '복구 여부': {'status': {'name': recovery}},
                '소유주 알림': {'checkbox': recovery == 'pending'}
            }
        }
        
        # None 값 제거
        payload['properties'] = {k: v for k, v in payload['properties'].items() if v is not None}
        
        try:
            response = requests.post(
                f'https://api.notion.com/v1/pages',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                print(f"✅ 에러 로그 저장 완료: {payload['properties']['에러 ID']['title'][0]['text']['content']}")
                return True
            else:
                print(f"❌ Notion API 오류: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ 에러 로그 저장 실패: {e}")
            return False

# 사용 예시
if __name__ == "__main__":
    logger = NotionErrorLogger()
    
    # 테스트 에러 로그
    logger.log_error(
        error_type="HTTPError",
        message="API 429 Too Many Requests",
        stack_trace="Traceback (most recent call last):\n  File 'test.py', line 10, in <module>\n    response = requests.get(url)\nrequests.exceptions.HTTPError: 429 Too Many Requests",
        model="gemini-2.0-flash",
        http_status=429,
        retry_count=1,
        recovery="pending"
    )
