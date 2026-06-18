from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class ImageSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        attr = dict(attrs)
        src = attr.get("src")
        if src:
            self.images.append(src)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    index = root / "index.html"
    errors: list[str] = []
    if not index.exists():
        errors.append("index.html 不存在")
        print_report(errors)
        return 1

    html = index.read_text(encoding="utf-8")
    parser = ImageSrcParser()
    parser.feed(html)
    missing = []
    for src in parser.images:
        if src.startswith(("http://", "https://", "data:")):
            continue
        if not (root / src).exists():
            missing.append(src)
    if missing:
        errors.append(f"缺失图片引用 {len(missing)} 个，例如 {missing[:5]}")

    question_bank = json.loads((root / "data" / "question_bank.json").read_text(encoding="utf-8"))
    knowledge_map = json.loads((root / "data" / "knowledge_map.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((root / "data" / "source_manifest.json").read_text(encoding="utf-8"))
    if len(question_bank) < 10:
        errors.append(f"题库条目过少：{len(question_bank)}")
    if len(knowledge_map) < 8:
        errors.append(f"知识点条目过少：{len(knowledge_map)}")
    if len(source_manifest.get("pages", [])) < 50:
        errors.append(f"截图页数过少：{len(source_manifest.get('pages', []))}")

    for required in ["HW2-2", "HW2-6", "HW2-7", "HW2-8", "HW2-11", "HW2-12", "HW2-14", "HW3-1", "HW3-2", "HW3-3", "HW3-9"]:
        if required not in {q["id"] for q in question_bank}:
            errors.append(f"缺少作业条目 {required}")

    forbidden_patterns = [
        r"C:\\Users\\",
        r"Desktop\\",
        r"1大学作业",
        r"digital-electronics-review-site",
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, html):
            errors.append(f"index.html 泄露本机或旧项目路径：{pattern}")

    for token in [".*", "./", ".^"]:
        if token in html:
            errors.append(f"公式区可能存在程序式符号：{token}")

    for token in ["id=\"searchInput\"", "id=\"imageModal\"", "class=\"prev\"", "class=\"next\"", "ArrowLeft", "ArrowRight"]:
        if token not in html:
            errors.append(f"缺少交互脚本/控件：{token}")

    if "double-important" not in html or "important" not in html:
        errors.append("缺少重点红框或双红框样式")

    print_report(errors)
    if errors:
        return 1
    print(f"通过：{len(knowledge_map)} 个知识点，{len(question_bank)} 个作业条目，{len(parser.images)} 个图片引用。")
    return 0


def print_report(errors: list[str]) -> None:
    if not errors:
        return
    print("审计失败：")
    for error in errors:
        print(f"- {error}")


if __name__ == "__main__":
    raise SystemExit(main())
