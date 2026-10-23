#!/usr/bin/env python3
"""VS Code · Continue 설정 무결성 검증 (PC·서버 공용).

수정 이력
- 2026-10-23: `import re` 가 함수 안에 있어 정적검사에서 미정의로 보이던 문제 수정, 미사용 임포트·변수 정리.
- 2026-10-23: PC 전용 경로 하드코딩 제거 → 후보 경로 목록으로 탐색(PC/서버 모두 동작).
- 2026-10-23: 이 호스트에 없는 파일은 FAIL 이 아니라 SKIP 으로 보고(거짓 실패 제거), PyYAML 미설치에도 죽지 않게 처리.
- 2026-10-23: `.vscode/settings.json` (JSONC) 도 검증 대상에 포함.

사용(Windows CMD):  python validate_configs.py
사용(Linux):        python3 validate_configs.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

try:
    import yaml  # 선택 의존성 — 없으면 YAML 검증만 건너뛴다
except ImportError:
    yaml = None

# 하드코딩 비밀값 탐지 패턴
KEY_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9]{8,}"),          # OpenRouter
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                # OpenAI 계열
    re.compile(r"AQ\.[A-Za-z0-9_-]{10,}"),             # Gemini
    re.compile(r"ntn_[A-Za-z0-9]{10,}"),               # Notion
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),               # GitHub PAT
    re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}\b"),      # Telegram bot 토큰
)

HOME = pathlib.Path.home()
REPO_CANDIDATES = (
    HOME / ".hermes" / "github_workspace" / "telegrambot_code",   # 소유주 PC 실제 경로
    HOME / "work" / "telegrambot_code",                           # 서버 사본
    pathlib.Path.cwd(),
)
CONFIG_CANDIDATES = {
    "CONTINUE_CONFIG": [
        HOME / ".hermes" / "github_workspace" / "telegrambot_code" / ".continue" / "config.yaml",
        HOME / ".continue" / "config.yaml",
    ],
    "CONTINUERC_JSON": [
        HOME / ".hermes" / "github_workspace" / "telegrambot_code" / ".continuerc.json",
    ],
}
VSCODE_JSON = ".vscode/settings.json"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def strip_jsonc(text: str) -> str:
    """VS Code 설정 파일은 JSONC — 주석과 마지막 쉼표를 제거해 표준 JSON 으로 만든다."""
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r",\s*([}\]])", r"\1", text)


def validate_json(path: pathlib.Path) -> tuple[str, str | None]:
    try:
        json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
        return PASS, None
    except json.JSONDecodeError as e:
        return FAIL, f"JSON 문법 오류: {e}"
    except Exception as e:
        return FAIL, f"{type(e).__name__}: {e}"


def validate_yaml(path: pathlib.Path) -> tuple[str, str | None]:
    if yaml is None:
        return SKIP, "PyYAML 미설치 — YAML 검증 생략(pip install pyyaml)"
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        return PASS, None
    except Exception as e:
        return FAIL, f"YAML 오류: {e}"


def scan_hardcoded_keys(path: pathlib.Path) -> tuple[str, str | None]:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return FAIL, f"{type(e).__name__}: {e}"
    hits = []
    for rx in KEY_PATTERNS:
        for m in rx.finditer(content):
            hits.append(m.group(0)[:12] + "…")
    if hits:
        return FAIL, f"하드코딩 키 의심 {len(hits)}건: {hits[:3]}"
    return PASS, None


def first_existing(paths) -> pathlib.Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def main() -> int:
    rows: list[tuple[str, str, str | None]] = []
    print("=" * 60)
    print("VS Code · Continue 설정 검증 (PC/서버 공용)")
    print("=" * 60)
    print(f"호스트: {sys.platform} · 홈: {HOME}")

    # 1) Continue 설정 (YAML)
    for label, paths in CONFIG_CANDIDATES.items():
        found = first_existing(paths)
        if found is None:
            rows.append((label, SKIP, "이 호스트에 없음(다른 위치: " + str(paths[0]) + ")"))
            continue
        status, err = (validate_yaml if found.suffix in (".yaml", ".yml") else validate_json)(found)
        print(f"  {label}: {status} · {found}")
        if status == PASS:
            k_status, k_err = scan_hardcoded_keys(found)
            rows.append((f"{label}_KEYS", k_status, k_err))
        rows.append((label, status, err))

    # 2) 저장소 .vscode/settings.json (+ 그 밖의 JSON 설정)
    repo = first_existing(REPO_CANDIDATES)
    if repo is None:
        rows.append(("VSCODE_SETTINGS", FAIL, "저장소 경로를 찾지 못함"))
    else:
        settings = repo / VSCODE_JSON
        if settings.exists():
            status, err = validate_json(settings)
            rows.append(("VSCODE_SETTINGS", status, err))
        else:
            rows.append(("VSCODE_SETTINGS", SKIP, f"없음: {settings}"))
        # 3) .gitignore 에 .continue/config.yaml 이 들어 있는지(비밀 설정 커밋 방지)
        gi = repo / ".gitignore"
        if gi.exists():
            text = gi.read_text(encoding="utf-8", errors="ignore")
            ok = ".continue" in text and ".env" in text
            rows.append(("GITIGNORE", PASS if ok else FAIL,
                         None if ok else ".continue 또는 .env 항목 누락"))
        else:
            rows.append(("GITIGNORE", FAIL, f".gitignore 없음: {gi}"))

    # 4) 요약
    print("\n" + "=" * 60)
    print("검증 결과 요약")
    print("=" * 60)
    failed = 0
    for name, status, err in rows:
        mark = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}[status]
        print(f"{name:22s} {mark}")
        if err:
            print(f"{'':22s} → {err[:110]}")
        failed += 1 if status == FAIL else 0
    print("=" * 60)
    if failed:
        print(f"실패 {failed}건 — 위 항목을 수정해야 합니다(이 호스트에 없는 파일은 SKIP 으로 표시)")
        return 1
    print("치명적 오류 없음 (SKIP 은 이 호스트에 파일이 없다는 뜻)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
