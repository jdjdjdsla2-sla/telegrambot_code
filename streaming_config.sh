# Python 실시간 스트리밍 설정
# Python Unbuffered Output Configuration

# 환경변수 설정
export PYTHONUNBUFFERED=1
export HERMES_STREAMING=1

# Python 실행 시 실시간 출력 보장
python -u script.py

# 또는 PYTHONUNBUFFERED 환경변수로 실행
PYTHONUNBUFFERED=1 python script.py

# VS Code terminal settings
{
  "terminal.integrated.env.windows": {
    "PYTHONUNBUFFERED": "1",
    "HERMES_STREAMING": "1"
  }
}
