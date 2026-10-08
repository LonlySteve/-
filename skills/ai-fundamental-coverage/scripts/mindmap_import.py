#!/usr/bin/env python3
"""把 EdrawMind (.emmx) 思维导图解析成节点台账。

只在题库需要"重新烘焙"时使用（见 SKILL.md「题库更新」一节）。
日常查股票不需要跑这个脚本。

用法：
    python3 mindmap_import.py <file.emmx> [--json out.json] [--md out.md]

输出 JSON 结构：
    {"doc_title": str, "pages": [{"page_id": str, "name": str, "nodes": [...]}]}
    每个 node: {id, type, text, parent, children[], depth, cy}
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

FLOATING_TYPES = {"FloatingTopic", "FloatingIdea", "CalloutTopic"}


def read_member(emmx: Path, name: str) -> str | None:
    """从 .emmx（zip）里读出某个成员文本；拿不到返回 None。"""
    with zipfile.ZipFile(emmx) as z:
        try:
            return z.read(name).decode("utf-8")
        except KeyError:
            return None


def _text_of(shape: ET.Element) -> str:
    """节点正文：优先取 <tp>（段落），失败再退回 <Text> 直连文本。"""
    parts: list[str] = []
    for tp in shape.iter("tp"):
        seg = "".join(tp.itertext()).strip()
        if seg:
            parts.append(seg)
    if not parts:
        for pp in shape.iter("pp"):
            seg = "".join(pp.itertext()).strip()
            if seg:
                parts.append(seg)
    return "\n".join(parts).strip()


def _num(shape: ET.Element, tag: str) -> float | None:
    el = shape.find(f"./Transform/{tag}")
    if el is None:
        return None
    v = el.get("V")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def parse_page(root: ET.Element, page_id: str) -> dict:
    shapes: dict[str, dict] = {}
    order: list[str] = []

    for shape in root.iter("Shape"):
        if shape.get("Type") == "MMConnector":
            continue
        sid = shape.get("ID")
        if not sid or sid == page_id:
            continue
        stype = shape.get("Type") or ""
        super_el = shape.find("./LevelData/Super")
        parent = super_el.get("V") if super_el is not None else None
        shapes[sid] = {
            "id": sid,
            "type": stype,
            "text": _text_of(shape),
            "parent_raw": parent,
            "cy": _num(shape, "CY"),
            "cx": _num(shape, "CX"),
            "kind": "floating" if stype in FLOATING_TYPES else "central",
            "children": [],
        }
        order.append(sid)

    # 父指针若指向页面本身或指向不存在的节点，则视为该页的根
    for sid in order:
        node = shapes[sid]
        p = node["parent_raw"]
        if p and p in shapes and p != sid:
            shapes[p]["children"].append(sid)
        else:
            node["parent_raw"] = None

    # 同级按纵向位置排序，贴近导图上"从上到下"的阅读顺序
    def sort_key(sid: str):
        cy = shapes[sid]["cy"]
        return (cy if cy is not None else 0.0, shapes[sid]["cx"] or 0.0)

    for node in shapes.values():
        node["children"].sort(key=sort_key)

    roots = [sid for sid in order if shapes[sid]["parent_raw"] is None]

    def walk(sid: str, depth: int, out: list[dict]) -> None:
        node = shapes[sid]
        out.append(
            {
                "id": sid,
                "type": node["type"],
                "kind": node["kind"],
                "text": node["text"],
                "parent": node["parent_raw"],
                "depth": depth,
                "cy": node["cy"],
                "children": list(node["children"]),
            }
        )
        for child in node["children"]:
            walk(child, depth + 1, out)

    flat: list[dict] = []
    for r in roots:
        walk(r, 0, flat)

    by_id = {n["id"]: n for n in flat}
    for n in flat:
        n["parent_text"] = by_id[n["parent"]]["text"] if n["parent"] in by_id else None

    return {
        "page_id": page_id,
        "name": root.get("Name"),
        "roots": roots,
        "nodes": flat,
    }


def parse_emmx(path: Path) -> dict:
    xml_text = read_member(path, "page/page.xml")
    if xml_text is None:
        raise SystemExit(f"不是有效的 .emmx（缺少 page/page.xml）: {path}")
    root = ET.fromstring(xml_text)

    doc = read_member(path, "document.xml")
    title = None
    if doc:
        try:
            droot = ET.fromstring(doc)
            creator = droot.find(".//Creator")
            title = creator.get("V") if creator is not None else None
        except ET.ParseError:
            pass

    pages = [parse_page(root, root.get("ID") or "page")]
    return {"doc_title": title, "source": str(path), "pages": pages}


def to_markdown(data: dict) -> str:
    lines: list[str] = []
    for page in data["pages"]:
        lines.append(f"# {page['name'] or page['page_id']}")
        lines.append("")
        by_id = {n["id"]: n for n in page["nodes"]}

        def emit(nid: str) -> None:
            n = by_id[nid]
            tag = "Floating" if n["kind"] == "floating" else n["type"]
            lines.append("    " * n["depth"] + f"- [{tag}] {n['text']}")
            for c in n["children"]:
                emit(c)

        for r in page["roots"]:
            emit(r)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="解析 .emmx 思维导图为节点台账")
    ap.add_argument("emmx", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--md", type=Path)
    args = ap.parse_args()

    if not args.emmx.exists():
        raise SystemExit(f"文件不存在: {args.emmx}")

    data = parse_emmx(args.emmx)
    total = sum(len(p["nodes"]) for p in data["pages"])
    for p in data["pages"]:
        print(f"页 {p['name']}({p['page_id']}): {len(p['nodes'])} 个节点, {len(p['roots'])} 个根")
    print(f"合计节点数: {total}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写 {args.json}")
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(to_markdown(data), encoding="utf-8")
        print(f"已写 {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
