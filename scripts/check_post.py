"""포스팅 PR 검사 (plan M6.2). 표준 라이브러리만 쓴다.

검사 내용
  - 바뀐 파일이 모두 `posts/weekNN/<slug>.md` 형식이다 (slug: 영문 소문자·숫자·하이픈)
  - 포스팅 파일을 지우지 않는다
  - front matter(첫 줄 `---` ~ 다음 `---`)에 week, chapters, nickname이 남아 있다
  - front matter의 week가 경로의 주차와 같다

사용법: python check_post.py <PR 머지 커밋을 checkout한 디렉터리>
실패하면 한국어 안내를 출력하고 종료 코드 1로 끝난다.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

POST_PATH = re.compile(r"^posts/week(\d{2})/([a-z0-9][a-z0-9-]*)\.md$")
KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:(.*)$")
REQUIRED_KEYS = ("week", "chapters", "nickname")
HELP = ("고치는 방법: PR의 'Files changed' 탭에서 봇이 처음 만든 내용과 비교해 경로와 맨 위 --- 사이의 "
        "front matter를 원래대로 되돌린 뒤 다시 커밋해 주세요. 본문은 자유롭게 고쳐도 돼요.")


def front_matter(text: str) -> dict[str, str] | None:
    """맨 위 `---` 사이의 최상위 `key: value`를 읽는다. front matter가 없으면 None."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        m = KEY_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2).split(" #", 1)[0].strip().strip("'\"").strip()
    return None  # 닫는 --- 없음


def check_path(path: str) -> list[str]:
    if POST_PATH.match(path):
        return []
    return [f"`{path}`: 이 PR에서는 `posts/weekNN/<이름>.md` 파일만 바꿀 수 있어요. "
            "다른 파일의 변경은 되돌려 주세요."]


def check_post(path: str, text: str) -> list[str]:
    m = POST_PATH.match(path)
    if not m:
        return check_path(path)
    fm = front_matter(text)
    if fm is None:
        return [f"`{path}`: 파일 맨 위의 front matter(--- 로 시작하고 --- 로 끝나는 부분)가 없어졌어요."]
    errors = [f"`{path}`: front matter에서 `{key}` 항목이 없어졌어요." for key in REQUIRED_KEYS if key not in fm]
    if "nickname" in fm and not fm["nickname"]:
        errors.append(f"`{path}`: front matter의 `nickname`이 비어 있어요.")
    if "week" in fm:
        week = fm["week"]
        if not week.isdigit() or int(week) != int(m.group(1)):
            errors.append(f"`{path}`: front matter의 week({week or '빈 값'})가 경로의 주차(week{m.group(1)})와 달라요.")
    return errors


BRANCH = re.compile(r"^post/week(\d{2})-([a-z0-9][a-z0-9-]*)$")


def branch_owns(branch: str, path: str) -> bool:
    """봇이 만든 초안 PR 브랜치 post/weekNN-<slug>는 posts/weekNN/<slug>.md 하나만 고칠 수 있다."""
    b, m = BRANCH.match(branch), POST_PATH.match(path)
    return bool(b and m and b.groups() == m.groups())


def check(changes: list[tuple[str, str]], read, branch: str | None = None) -> list[str]:
    """changes: (git 상태 문자, 경로) 목록. read(path)는 PR 쪽 파일 내용을 돌려준다.
    branch가 있으면 다른 사람의 파일(다른 slug)을 고치지 못하게 브랜치와 경로를 맞춰 본다."""
    errors: list[str] = []
    for status, path in changes:
        if branch is not None and POST_PATH.match(path) and not branch_owns(branch, path):
            errors.append(f"`{path}`: 이 PR(`{branch}`)에서는 자기 포스팅 파일만 고칠 수 있어요.")
            continue
        if not POST_PATH.match(path):
            errors += check_path(path)
        elif status.startswith("D"):
            errors.append(f"`{path}`: 포스팅 파일은 지울 수 없어요. 지운 파일을 되살려 주세요.")
        else:
            errors += check_post(path, read(path))
    return errors


def changed_files(repo: Path) -> list[tuple[str, str]]:
    """PR 머지 커밋(HEAD)과 base(HEAD^1) 사이에 바뀐 파일."""
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "-z", "--name-status", "--no-renames", "HEAD^1", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    parts = [p for p in out.split("\0") if p]
    return list(zip(parts[0::2], parts[1::2]))


def main(argv: list[str]) -> int:
    repo = Path(argv[1] if len(argv) > 1 else ".")
    branch = os.environ.get("POST_BRANCH") or None  # 워크플로가 github.head_ref를 env로 넘긴다
    errors = check(changed_files(repo), lambda p: (repo / p).read_text(encoding="utf-8"), branch)
    if not errors:
        print("포스팅 검사 통과")
        return 0
    print("포스팅 검사에 실패했어요.")
    for e in errors:
        print(f"- {e}")
    print(HELP)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
