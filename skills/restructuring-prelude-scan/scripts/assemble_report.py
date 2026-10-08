#!/usr/bin/env python3
"""按题库顺序装配报告：顺序、标题、核对项全部由 bank.json 决定，模型只提供正文。

因此"合并作答""漏节点"在装配层不可能发生：缺的片段会写成显式缺口占位，绝不静默吞掉。

用法：
    python3 assemble_report.py --run <运行目录>

产物：report.md（主交付物）、assembly.json（装配诊断）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ELEMENT_RE = re.compile(r"^\s*(?:[-*+]\s*)?\*\*(?P<label>[^*]+?)\*\*\s*[:：]\s*(?P<value>.*)$")
# 注意：必须带 re.MULTILINE —— 补丁文件 blocks/<id>.md 的标题行是整份文件的一行，
# 缺 MULTILINE 时 `^...$` 无法命中该行，标题会被当正文塞回 analysis，进而在 report.md 里
# 生成重复的 `### [id]` 标题，使 coverage_check 的分段被重置、整个节点的核对项被判缺失。
HEADING_RE = re.compile(
    r"^\s{0,3}#{2,4}\s*\[(?P<id>[A-Za-z0-9]+)\]\s*(?P<title>.*)$", re.MULTILINE
)
MODULE_RE = re.compile(r"^\s{0,3}#{1,4}\s*(?P<title>.*)$")
# 补漏文件必须按节点 ID 命名（如 F19.md）。其余文件名一律忽略 —— 否则 agent 用核对项
# 名称（如 needs_input.md）建的文件会被当成合法区块塞进报告。
PATCH_NAME_RE = re.compile(r"^[A-Za-z]\d{1,3}$")


def collect_blocks(run_dir: Path) -> dict[str, str]:
    """把所有 parts/*.md 与 blocks/*.md 里的区块收集成 {item_id: 正文}。

    优先级：blocks/<id>.md（定点补漏）> parts/*.md 里的 [id] 区块。
    """
    blocks: dict[str, str] = {}

    for part in sorted((run_dir / "parts").glob("*.md")):
        text = part.read_text(encoding="utf-8", errors="replace")
        current_id: str | None = None
        buf: list[str] = []

        def flush() -> None:
            if current_id and current_id not in blocks:
                blocks[current_id] = "\n".join(buf).strip()

        for line in text.splitlines():
            m = HEADING_RE.match(line)
            if m:
                flush()
                current_id = m.group("id").upper()
                buf = []
            elif current_id is not None:
                buf.append(line)
        flush()

    for patch in sorted((run_dir / "blocks").glob("*.md")):
        pid = patch.stem.upper()
        if not PATCH_NAME_RE.match(pid):
            continue  # 非节点 ID 命名的文件不是补丁，直接忽略
        body = patch.read_text(encoding="utf-8", errors="replace")
        m = HEADING_RE.search(body)
        if m and m.group("id").upper() == pid:
            # 补丁文件常自带提纲表头（# 模块名 / 标的 / --- 等）；只保留标题行之后的正文，
            # 否则重复的 `### [id]` 会让下游分段错乱、把整条答案判成缺失。
            body = body[m.end():]
        blocks[pid] = body.strip()

    return blocks


def parse_block(body: str, expected: set[str] | None = None) -> tuple[dict[str, str], list[str], str]:
    """把区块正文拆成：核对项 {label: value}、核对项顺序、剩余分析文本。

    expected 给出该节点在题库里的合法核对项名称。只有命中题库的行才被当作核对项，
    其余（例如分析段里的 `**A. 框架**：…` 这类粗体小标题）原样留在分析里，
    避免"把正文抽走"造成静默吞内容。
    """
    elements: dict[str, str] = {}
    order: list[str] = []
    analysis: list[str] = []

    for line in body.splitlines():
        m = ELEMENT_RE.match(line)
        if m:
            label = m.group("label").strip()
            if expected is not None and label not in expected:
                analysis.append(line)
                continue
            value = m.group("value").strip()
            if label not in elements:
                order.append(label)
            elements[label] = value
        else:
            analysis.append(line)

    analysis_text = "\n".join(analysis).strip()
    # 去掉仅剩的分节标题噪音（如 #### 分析）
    analysis_text = re.sub(r"^#{2,4}\s*分析\s*$", "", analysis_text, flags=re.M).strip()
    return elements, order, analysis_text


def has_table(text: str) -> bool:
    rows = [ln for ln in text.splitlines() if ln.count("|") >= 2]
    return len(rows) >= 3


def count_table_rows(text: str) -> int:
    rows = [ln for ln in text.splitlines() if ln.count("|") >= 2]
    # 去掉 |---|---| 分隔行
    return len([r for r in rows if not re.fullmatch(r"[\s|:\-]+", r)])


def build_report(run_dir: Path) -> tuple[str, dict]:
    bank = json.loads((run_dir / "bank.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    blocks = collect_blocks(run_dir)

    total_items = sum(len(m["items"]) for m in bank["modules"])
    total_els = sum(len(i["elements"]) for m in bank["modules"] for i in m["items"])

    out: list[str] = []
    diag: dict = {"items": {}, "modules": [], "counts": {"items": total_items, "elements": total_els}}

    out.append(f"# {bank.get('skill_title', bank['bank_name'])} · 逐节点全覆盖分析")
    out.append("")
    out.append(f"- **标的**：{meta['name']}（{meta['ticker']}）")
    out.append(f"- **市场**：{meta['market']}")
    out.append(f"- **数据基准日**：{meta['as_of']}")
    if meta.get("window_start"):
        out.append(f"- **观察窗口**：{meta['window_start']} ~ {meta['as_of']}"
                   f"（{meta.get('lookback_months', '')} 个月）")
    src = bank.get("source", {})
    if src.get("total_nodes"):
        scope = (f"导图 {src['total_nodes']} 节点中，本次范围内的 {src.get('in_scope_nodes', total_items)} 节点"
                 f" → 切片为 {total_items} 个必答节点")
    elif src.get("subtree"):
        scope = (f"{src['subtree']} 共 {src.get('subtree_nodes', '?')} 节点"
                 f" → 切片为 {total_items} 个必答节点")
    else:
        scope = f"切片为 {total_items} 个必答节点"
    out.append(f"- **题库**：{bank['bank_name']}（{scope} / {total_els} 个原子核对项）")
    out.append(f"- **装配时间**：{datetime.now().isoformat(timespec='seconds')}")
    out.append("")
    out.append("> 装配规则：标题、顺序、核对项清单全部由 `bank.json` 决定；"
               "模型只提供正文。缺失片段一律显式写成 `（缺口：未作答）`，不静默省略。")
    out.append("")

    for module in bank["modules"]:
        module_diag = {"id": module["id"], "title": module["title"], "items": []}
        out.append(f"## {module['id']} {module['title']}")
        out.append("")

        for item in module["items"]:
            body = blocks.get(item["id"], "")
            expected = {e["label"] for e in item["elements"]}
            elements, order, analysis = parse_block(body, expected)
            out.append(f"### [{item['id']}] {item['source_text']}")
            out.append("")

            if item.get("needs_input"):
                out.append("> ⚠️ 原图该节点含未填写占位（`xxx`）：本条按通用框架作答，"
                           "补齐输入后可定点重跑。")
                out.append("")

            found, missing = 0, []
            for el in item["elements"]:
                val = elements.get(el["label"], "")
                if val:
                    found += 1
                else:
                    missing.append(el["label"])
                shown = val if val else "（缺口：未作答）"
                out.append(f"- **{el['label']}**：{shown}")
            out.append("")

            if analysis:
                out.append("#### 分析")
                out.append("")
                out.append(analysis)
                out.append("")

            extra = [lbl for lbl in order if lbl not in {e["label"] for e in item["elements"]}]
            diag["items"][item["id"]] = {
                "module": module["id"],
                "elements_total": len(item["elements"]),
                "elements_filled": found,
                "missing": missing,
                "unknown_labels": extra,
                "block_found": bool(body),
                "block_chars": len(body),
                "has_table": has_table(body),
                "table_rows": count_table_rows(body),
            }
            module_diag["items"].append({
                "id": item["id"], "filled": found, "total": len(item["elements"]),
                "missing": missing, "block_found": bool(body),
            })

        # 题库指定的模块之后，追加汇总表（总表 + 汇总核对项）
        if module["id"] == bank.get("rubric", {}).get("after_module"):
            rubric = bank["rubric"]
            rb_id = rubric["id"]
            out.append(f"### [{rb_id}] {rubric['title']}")
            out.append("")
            out.append(f"> {rubric['note']}")
            out.append("")
            rb_body = blocks.get(rb_id, "")
            extras = rubric.get("extra_required", [])
            if rb_body:
                out.append(rb_body)
                out.append("")
            else:
                cols = rubric.get("columns") or ["维度", "判定标准", "实际数据", "结论"]
                out.append("| " + " | ".join(cols) + " |")
                out.append("| " + " | ".join("---" for _ in cols) + " |")
                for d in rubric["dimensions"]:
                    row = [d["label"]] + ["（缺口：未作答）"] * (len(cols) - 1)
                    out.append("| " + " | ".join(row) + " |")
                out.append("")
                for e in extras:
                    out.append(f"- **{e['label']}**：（缺口：未作答）")
                out.append("")
            diag["items"][rb_id] = {
                "module": module["id"],
                "elements_total": len(rubric["dimensions"]) + len(extras),
                "elements_filled": 0,
                "missing": [],
                "block_found": bool(rb_body),
                "block_chars": len(rb_body),
                "has_table": has_table(rb_body),
                "table_rows": count_table_rows(rb_body),
                "rubric": True,
            }

        diag["modules"].append(module_diag)

    report = "\n".join(out).rstrip() + "\n"
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    (run_dir / "assembly.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, diag


def main() -> int:
    ap = argparse.ArgumentParser(description="按题库装配全覆盖报告")
    ap.add_argument("--run", type=Path, required=True)
    args = ap.parse_args()

    run_dir = args.run.expanduser().resolve()
    if not (run_dir / "bank.json").exists():
        raise SystemExit(f"不是运行目录（缺 bank.json）: {run_dir}")

    report, diag = build_report(run_dir)
    filled = sum(v["elements_filled"] for v in diag["items"].values())
    total = sum(v["elements_total"] for v in diag["items"].values())
    print(f"已写 {run_dir / 'report.md'}")
    print(f"装配统计：核对项 {filled}/{total} 已填，"
          f"{len(diag['items'])} 个节点区块")
    empty = [k for k, v in diag["items"].items() if not v.get("block_found")]
    if empty:
        print(f"未找到作答的节点：{', '.join(empty)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
