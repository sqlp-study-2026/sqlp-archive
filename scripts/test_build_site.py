"""build_site.py 테스트: 원고 생성과 공개 금지 키 검사."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_site  # noqa: E402

DATA = {
    "goal": {"name": "친절한 SQL 튜닝 1회독", "start_date": "2026-10-01", "end_date": "2027-09-30",
             "exam_date": None, "total_chapters": 7, "weights": {"post": 40, "lab": 60}},
    "overall": {"annual_pct": 35.0, "chapters_done_avg": 1.5, "weekly": [{"week": 1, "pct": 66.7}]},
    "members": [{"nickname": "하늘", "annual_pct": 31.4, "chapters_done": 2,
                 "weekly": [{"week": 1, "done": 2, "total": 3, "pct": 66.7}]}],
    "criteria": [{"id": "pass", "name": "실습 PASS", "method": "metric", "target": 5, "unit": "개",
                  "value": 3, "achieved": False}],
    "curriculum": {"chapters": [{"id": 1, "title": "1장"}], "weeks": [
        {"number": 1, "title": "1장", "start": "2026-10-04T00:00:00+09:00", "end": "2026-10-10T23:59:59+09:00",
         "chapters": [1], "problems": [{"id": "T001", "title": "사번 범위 조회", "chapter": 1},
                                       {"id": "T002", "title": "", "chapter": 1}]}]},
}


def make_root(tmp_path, data=DATA):
    (tmp_path / "data" / "problems").mkdir(parents=True)
    (tmp_path / "data" / "progress.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "data" / "problems" / "T001.md").write_text("# T001 사번 범위 조회\n", encoding="utf-8")
    (tmp_path / "posts" / "week01").mkdir(parents=True)
    (tmp_path / "posts" / "week01" / "sky.md").write_text(
        "---\nweek: 1\nchapters: [1]\nnickname: 하늘\n---\n\n# 1장 정리\n\n본문\n", encoding="utf-8")
    (tmp_path / "posts" / "week01" / "Bad Name.md").write_text("무시", encoding="utf-8")
    return tmp_path


def test_build_writes_home_curriculum_problems_posts(tmp_path):
    root = make_root(tmp_path)
    assert build_site.build(root, root / "_docs") == []
    docs = root / "_docs"
    home = (docs / "index.md").read_text(encoding="utf-8")
    assert "전체 진행률 35.0%" in home and "| 하늘 | 31.4% | 2 | 1주차 2/3 |" in home and "⬜ 실습 PASS" in home
    cur = (docs / "curriculum.md").read_text(encoding="utf-8")
    assert "[T001 사번 범위 조회](problems/T001.md)" in cur and "- T002\n" in cur  # 페이지 없는 문제는 링크 없음
    assert (docs / "problems" / "T001.md").exists()
    post = (docs / "posts" / "week01" / "sky.md").read_text(encoding="utf-8")
    assert post.startswith("> 1주차 · 하늘 · 1장") and "nickname:" not in post and "# 1장 정리" in post
    assert not (docs / "posts" / "week01" / "Bad Name.md").exists()


def test_forbidden_keys_block_the_build(tmp_path):
    leaked = json.loads(json.dumps(DATA))
    leaked["members"][0]["login"] = "kim-gh"
    leaked["members"][0]["weekly"][0]["verdict"] = "PASS"
    root = make_root(tmp_path, leaked)
    errors = build_site.build(root, root / "_docs")
    assert errors and ".members[0].login" in errors[0] and "verdict" in errors[0]
    assert not (root / "_docs").exists()


def test_no_data_yet_still_builds_placeholder_home(tmp_path):
    (tmp_path / "posts").mkdir()
    assert build_site.build(tmp_path, tmp_path / "_docs") == []
    assert "아직 공개된 진행률이 없어요" in (tmp_path / "_docs" / "index.md").read_text(encoding="utf-8")


def test_main_exit_code(tmp_path, capsys):
    leaked = json.loads(json.dumps(DATA))
    leaked["answer"] = "SELECT"
    assert build_site.main([str(make_root(tmp_path, leaked))]) == 1
    assert "answer" in capsys.readouterr().err


def test_author_comes_from_slug_not_front_matter(tmp_path):
    root = make_root(tmp_path)
    (root / "data" / "authors.json").write_text('{"sky": "하늘"}', encoding="utf-8")
    post = root / "posts" / "week01" / "sky.md"
    post.write_text(post.read_text(encoding="utf-8").replace("nickname: 하늘", "nickname: 바다"), encoding="utf-8")
    build_site.build(root, root / "_docs")
    page = (root / "_docs" / "posts" / "week01" / "sky.md").read_text(encoding="utf-8")
    assert page.startswith("> 1주차 · 하늘 ·")
