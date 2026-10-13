import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import check_post  # noqa: E402

GOOD = "---\nweek: 3\nchapters: [3]\nnickname: \"하늘\"\n---\n\n# 3장 전반\n본문\n"
PATH = "posts/week03/haneul.md"


def test_valid_post_passes():
    assert check_post.check([("M", PATH)], lambda p: GOOD) == []


def test_block_list_chapters_and_quoted_week():
    text = "---\nweek: '03'\nchapters:\n  - 3\n  - 4\nnickname: 하늘\n---\n본문"
    assert check_post.check_post(PATH, text) == []


@pytest.mark.parametrize("path", [
    "posts/week3/haneul.md",
    "posts/week03/Haneul.md",
    "posts/week03/sub/haneul.md",
    "posts/week03/haneul.txt",
    "posts/haneul.md",
    "mkdocs.yml",
    ".github/workflows/notify.yml",
])
def test_bad_paths_fail(path):
    assert check_post.check([("A", path)], lambda p: GOOD)


@pytest.mark.parametrize("key", ["week", "chapters", "nickname"])
def test_missing_key_fails(key):
    text = "\n".join(l for l in GOOD.splitlines() if not l.startswith(key)) + "\n"
    errors = check_post.check_post(PATH, text)
    assert any(f"`{key}`" in e for e in errors)


def test_week_mismatch_fails():
    errors = check_post.check_post(PATH, GOOD.replace("week: 3", "week: 4"))
    assert any("주차" in e for e in errors)


def test_missing_front_matter_fails():
    assert check_post.check_post(PATH, "# 제목\n본문\n")
    assert check_post.check_post(PATH, "---\nweek: 3\n본문\n")  # 닫는 --- 없음


def test_empty_nickname_fails():
    assert check_post.check_post(PATH, GOOD.replace('nickname: "하늘"', "nickname:"))


def test_deleting_post_fails():
    assert check_post.check([("D", PATH)], lambda p: pytest.fail("deleted file must not be read"))


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_main_on_git_repo(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    post = tmp_path / PATH
    post.parent.mkdir(parents=True)
    post.write_text(GOOD, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "post")
    assert check_post.main(["check_post.py", str(tmp_path)]) == 0

    post.write_text(GOOD.replace("week: 3", "week: 9"), encoding="utf-8")
    (tmp_path / "README.md").write_text("y\n", encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "tamper")
    assert check_post.main(["check_post.py", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "README.md" in out and "week09" not in out and "week03" in out


def test_branch_may_only_touch_its_own_post():
    import check_post as cp
    good = "---\nweek: 1\nchapters: [1]\nnickname: 하늘\n---\n본문\n"
    read = lambda p: good
    assert cp.check([("M", "posts/week01/sky.md")], read, "post/week01-sky") == []
    errors = cp.check([("A", "posts/week01/sea.md")], read, "post/week01-sky")
    assert errors and "자기 포스팅 파일만" in errors[0]
    assert cp.check([("M", "posts/week02/sky.md")], read, "post/week01-sky")  # 다른 주차도 안 된다
    assert cp.check([("M", "posts/week01/sky.md")], read, "feature/x")  # 봇 브랜치가 아니면 안 된다
    assert cp.check([("M", "posts/week01/sky.md")], read, None) == []  # 브랜치를 모르면 기존 검사만
