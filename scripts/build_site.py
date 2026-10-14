"""공개 사이트 원고(_docs/)를 만든다 (plan M7, F6). 배포 워크플로가 mkdocs build 직전에 실행한다.

입력: data/progress.json, data/problems/*.md, data/posts.json (sqlp-judge rebuild가 push), posts/weekNN/*.md (머지된 포스팅)
출력: _docs/index.md, _docs/curriculum.md, _docs/problems/{id}.md, _docs/posts/index.md(포스팅 목록),
      _docs/posts/weekNN/{slug}.md (본문 + 리뷰)
표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_post import POST_PATH, front_matter  # noqa: E402

# 공개 데이터에 있으면 안 되는 키 (AC7.3 구조 검사). judge 쪽 허용 목록 내보내기의 2차 방어선.
FORBIDDEN_KEYS = {"login", "email", "path", "sql", "answer", "buffers", "verdict", "best",
                  "review_comments", "attempts", "issue"}


def forbidden_keys(value, trail="") -> list[str]:
    if isinstance(value, dict):
        out = [f"{trail}.{k}" for k in value if k in FORBIDDEN_KEYS]
        for k, v in value.items():
            out += forbidden_keys(v, f"{trail}.{k}")
        return out
    if isinstance(value, list):
        return [x for i, v in enumerate(value) for x in forbidden_keys(v, f"{trail}[{i}]")]
    return []


STATE_LABEL = {"draft": "✍️ 작성 중", "review": "👀 리뷰 중", "merged": "✅ 게시"}
VERDICT_LABEL = {"APPROVED": "✅ 승인", "CHANGES_REQUESTED": "🔁 수정 요청", "COMMENTED": "💬 의견"}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def posts_index(posts: list[dict], published: set[str]) -> str:
    """주차별 포스팅 목록. 게시(머지)된 글은 사이트 안 링크, 리뷰 대화는 GitHub PR 링크."""
    lines = ["# 포스팅", "", "주차별 스터디원 포스팅이에요. 리뷰는 게시된 글 아래와 GitHub PR에서 볼 수 있어요.", ""]
    if not posts:
        return "\n".join(lines + ["아직 포스팅이 없어요."]) + "\n"
    for week in sorted({p["week"] for p in posts}, reverse=True):
        items = sorted((p for p in posts if p["week"] == week), key=lambda p: p["nickname"])
        lines += [f"## {week}주차 · {items[0]['title']}", "", "| 닉네임 | 상태 | 글 | 리뷰 |", "|---|---|---|---|"]
        for p in items:
            rel = f"week{week:02d}/{p['slug']}.md"
            read = f"[읽기]({rel})" if rel in published else "-"
            lines.append(f"| {p['nickname']} | {STATE_LABEL.get(p['state'], p['state'])} | {read} "
                         f"| [PR #{p['pr']}]({p['url']}) |")
        lines.append("")
    return "\n".join(lines)


def review_section(info: dict) -> str:
    """머지된 포스팅 아래에 붙는 리뷰. 작성자는 닉네임(judge가 login을 바꿔서 보낸다)."""
    lines = ["", "---", "", "## 💬 리뷰", ""]
    if not info.get("reviews"):
        lines += ["남겨진 리뷰가 없어요.", ""]
    for r in info.get("reviews", []):
        head = f"**{r['author']}**"
        if r["kind"] == "review":
            head += f" · {VERDICT_LABEL.get(r.get('decision') or '', '리뷰')}"
        elif r["kind"] == "inline":
            head += " · 본문 코멘트"
        lines.append(head)
        if r.get("quote"):
            lines += ["", f"> {r['quote']}"]
        if r.get("body"):
            lines += ["", r["body"]]
        lines.append("")
    lines.append(f"[GitHub PR #{info['pr']}에서 전체 대화 보기]({info['url']})")
    return "\n".join(lines) + "\n"


def _bar(pct: float, cells: int = 10) -> str:
    filled = int(round(pct / 100 * cells))
    return "▓" * filled + "░" * (cells - filled)


def home(data: dict) -> str:
    g, o = data["goal"], data["overall"]
    lines = [f"# {g['name']}", "", "[📝 포스팅 모아 보기](posts/index.md) · [📚 커리큘럼](curriculum.md)", "",
             f"**전체 진행률 {o['annual_pct']}%** {_bar(o['annual_pct'])} · 평균 완료 챕터 {o['chapters_done_avg']}"
             f" / {g['total_chapters']}", "",
             f"기간 {g['start_date']} ~ {g['end_date']}" + (f" · SQLP 응시 목표일 {g['exam_date']}" if g["exam_date"] else ""),
             "", "## 스터디원별 진행률", "", "| 닉네임 | 연간 | 완료 챕터 | 최근 주차 |", "|---|---:|---:|---:|"]
    for m in data["members"]:
        last = m["weekly"][-1] if m["weekly"] else None
        recent = f"{last['week']}주차 {last['done']}/{last['total']}" if last else "-"
        lines.append(f"| {m['nickname']} | {m['annual_pct']}% | {m['chapters_done']} | {recent} |")
    if data["criteria"]:
        lines += ["", "## 성공 기준", ""]
        for c in data["criteria"]:
            mark = "✅" if c["achieved"] else "⬜"
            target = f" (목표 {c['target']}{c['unit']}, 현재 {c['value']})" if c["target"] is not None else ""
            lines.append(f"- {mark} {c['name']}{target}")
    if o["weekly"]:
        lines += ["", "## 주차별 달성률", "", "| 주차 | 달성률 |", "|---:|---:|"]
        lines += [f"| {w['week']} | {w['pct']}% |" for w in o["weekly"]]
    return "\n".join(lines) + "\n"


def curriculum(data: dict, problem_pages: set[str]) -> str:
    lines = ["# 커리큘럼", ""]
    for w in data["curriculum"]["weeks"]:
        lines += [f"## {w['number']}주차 · {w['title']}", "",
                  f"{w['start'][:10]} ~ {w['end'][:10]} · {', '.join(map(str, w['chapters']))}장", ""]
        for p in w["problems"]:
            label = f"{p['id']} {p['title']}".strip()
            lines.append(f"- [{label}](problems/{p['id']}.md)" if p["id"] in problem_pages else f"- {label}")
        lines.append("")
    return "\n".join(lines)


def post_page(text: str, author: str | None = None) -> str:
    """author가 있으면(data/authors.json) front matter의 nickname보다 우선한다. 다른 사람 이름을 사칭하지 못하게."""
    meta = front_matter(text) or {}
    body = text.split("---", 2)[2].lstrip("\n") if text.startswith("---") else text
    chapters = meta.get('chapters', '').strip('[] ')
    tag = f"> {meta.get('week', '?')}주차 · {author or meta.get('nickname', '')} · {chapters}장"
    return tag + "\n\n" + body


def build(root: Path, out: Path) -> list[str]:
    """원고를 만들고 문제(오류 메시지 목록)를 돌려준다. 문제가 있으면 아무것도 쓰지 않는다."""
    data = _load(root / "data" / "progress.json")
    posts = (_load(root / "data" / "posts.json") or {}).get("posts", [])
    if bad := forbidden_keys(data or {}) + forbidden_keys(posts, "posts"):
        return [f"공개하면 안 되는 키가 있어요: {', '.join(bad)}"]
    if out.exists():
        shutil.rmtree(out)
    (out / "problems").mkdir(parents=True)
    problem_pages = set()
    for page in sorted((root / "data" / "problems").glob("*.md")):
        shutil.copyfile(page, out / "problems" / page.name)
        problem_pages.add(page.stem)
    if data is None:
        (out / "index.md").write_text("# SQLP 스터디 아카이브\n\n아직 공개된 진행률이 없어요.\n", encoding="utf-8")
    else:
        (out / "index.md").write_text(home(data), encoding="utf-8")
        (out / "curriculum.md").write_text(curriculum(data, problem_pages), encoding="utf-8")
    authors = _load(root / "data" / "authors.json") or {}
    info = {f"week{p['week']:02d}/{p['slug']}.md": p for p in posts}
    published = set()
    for post in sorted((root / "posts").glob("week*/*.md")):
        rel = post.relative_to(root).as_posix()
        if POST_PATH.match(rel):
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            page = post_page(post.read_text(encoding="utf-8"), authors.get(post.stem))
            key = rel.removeprefix("posts/")
            if key in info:
                page = page.rstrip("\n") + "\n" + review_section(info[key])
            target.write_text(page, encoding="utf-8")
            published.add(key)
    (out / "posts").mkdir(exist_ok=True)
    (out / "posts" / "index.md").write_text(posts_index(posts, published), encoding="utf-8")
    return []


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    errors = build(root, root / "_docs")
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
