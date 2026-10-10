#!/usr/bin/env python3
"""VS Code 3AI 설정 파일 무결성 검증 스크립트"""

import json
import yaml
import os
import sys
from pathlib import Path

def validate_json(filepath):
    """JSON 파일 검증"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ JSON VALID: {filepath}")
        return True, None
    except json.JSONDecodeError as e:
        print(f"❌ JSON ERROR: {filepath} - {e}")
        return False, str(e)
    except FileNotFoundError:
        print(f"❌ FILE NOT FOUND: {filepath}")
        return False, "File not found"

def validate_yaml(filepath):
    """YAML 파일 검증"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        print(f"✅ YAML VALID: {filepath}")
        return True, None
    except yaml.YAMLError as e:
        print(f"❌ YAML ERROR: {filepath} - {e}")
        return False, str(e)
    except FileNotFoundError:
        print(f"❌ FILE NOT FOUND: {filepath}")
        return False, "File not found"

def check_api_keys_in_code(filepath):
    """파일에서 API 키 하드코딩 체크"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        patterns = [
            r'sk-or-v1-[a-f0-9]+',  # OpenRouter key
            r'AQ\.[a-zA-Z0-9_-]+',  # Gemini key
            r'ntn_\w+',              # Notion key
        ]

        found_keys = []
        for pattern in patterns:
            matches = re.findall(pattern, content)
            found_keys.extend(matches)

        if found_keys:
            print(f"⚠️  API KEY FOUND in {filepath}: {len(found_keys)}개")
            return False, found_keys
        else:
            print(f"✅ NO HARDCODED KEYS: {filepath}")
            return True, None
    except Exception as e:
        print(f"❌ CHECK ERROR: {filepath} - {e}")
        return False, str(e)

def main():
    print("=" * 60)
    print("🔍 VS Code 3AI 설정 파일 무결성 검증 시작")
    print("=" * 60)

    results = []

    # 1. .continuerc.json 검증
    local_config = Path.home() / ".hermes" / "github_workspace" / "telegrambot_code" / ".continuerc.json"
    if local_config.exists():
        valid, error = validate_json(str(local_config))
        results.append(("LOCAL_CONFIG", valid, error))
    else:
        results.append(("LOCAL_CONFIG", False, "File not found"))

    # 2. ~/.continue/config.yaml 검증
    global_config = Path.home() / ".continue" / "config.yaml"
    if global_config.exists():
        valid, error = validate_yaml(str(global_config))
        results.append(("GLOBAL_CONFIG", valid, error))
    else:
        results.append(("GLOBAL_CONFIG", False, "File not found"))

    # 3. API 키 하드코딩 체크
    import re
    for config_path in [local_config, global_config]:
        if config_path.exists():
            valid, keys = check_api_keys_in_code(str(config_path))
            if keys:
                print(f"⚠️  Found API keys: {keys[:3]}...")  # Only show first 3

    # 4. .gitignore 체크
    gitignore = Path.home() / ".hermes" / "github_workspace" / "telegrambot_code" / ".gitignore"
    if gitignore.exists():
        with open(gitignore, 'r') as f:
            content = f.read()
        if '.continue/config.yaml' in content:
            print("✅ .gitignore contains .continue/config.yaml")
            results.append(("GITIGNORE", True, None))
        else:
            print("❌ .gitignore missing .continue/config.yaml")
            results.append(("GITIGNORE", False, "Missing entry"))
    else:
        print("❌ .gitignore not found")
        results.append(("GITIGNORE", False, "File not found"))

    # 5. 요약 보고
    print("\n" + "=" * 60)
    print("📊 검증 결과 요약")
    print("=" * 60)

    all_passed = True
    for test_name, passed, error in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20s} {status}")
        if error:
            print(f"                      Error: {error[:50]}...")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 모든 검증 통과! 시스템 안정화 완료")
        sys.exit(0)
    else:
        print("⚠️  일부 검증 실패 - 수정 필요")
        sys.exit(1)

if __name__ == "__main__":
    main()
