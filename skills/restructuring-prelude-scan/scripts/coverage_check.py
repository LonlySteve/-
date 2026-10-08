#!/usr/bin/env python3
"""覆盖率硬闸门：逐节点、逐原子核对项核对 report.md，不合格就退出码 1。

这一层不信任何"我已经覆盖全部"的说法，也不看 assembly.json（那是装配层的自述），
只解 report.md + bank.json，独立判定。

用法：
    python3 coverage_check.py --run <运行目录>
    echo "gate exit=$?"

产物：coverage_report.md、coverage.csv。退出码 0 = 可交付；1 = 必须补漏后重跑。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ELEMENT_RE = re.compile(r"^\s*(?:[-*+]\s*)?\*\*(?P<label>[^*]+?)\*\*\s*[:：]\s*(?P<value>.*)$")
ITEM_HEAD_RE = re.compile(r"^\s{0,3}#{2,4}\s*\[(?P<id>[A-Za-z0-9]+)\]")
MODULE_HEAD_RE = re.compile(r"^\s{0,3}##\s+(?P<title>.+?)\s*$")

GAP_RE = re.compile(r"未披露|未获取|未能获取|无法获取|未公开|未找到|未查到|无数据|不适用|缺失|待补|暂无|没有披露|N/?A")
GAP_SHORT_OK = re.compile(r"^(不适用|无|无减持|不涉及|暂无|报告期内无)")
# 装配层写的显式占位：它不是答案，必须先于任何长度/类型校验被拒
PLACEHOLDER = "（缺口：未作答）"
PATH_HINT_RE = re.compile(r"查|见|来源|公告|年报|半年报|季报|报告|披露|栏目|数据库|投关|说明会|Wind|同花顺|巨潮|交易所|SEC|EDGAR|不适用")
SOURCE_RE = re.compile(r"来源|公告|编号|公告名称|http|www\.|年报表|半年报|季报|说明会|投关|投资者关系|年报|第\s*\d+\s*号|20\d{2}[-/.]\d{1,2}")
FILLER_RE = re.compile(
    r"综合来看|整体来看|整体表现(良好|不错)|表现良好|值得关注|有待观察|有待进一步|具体情况(需|有待)|"
    r"较为稳健|比较稳健|表现不错|尚可|需持续关注|难以判断|无法判断"
)
DIGIT_RE = re.compile(r"\d")

MIN_BLOCK_CHARS = 100
MIN_ANALYSIS_CHARS = 0  # 分析段非必需
DEFAULT_RUBRIC_MIN_ROWS = 10  # 兜底值；实际以 bank.rubric.min_rows 为准


def parse_report(text: str) -> tuple[dict, list[str]]:
    """把 report.md 拆成 {item_id: {"elements": {...}, "block": str}}，并返回模块标题列表。"""
    sections: dict[str, dict] = {}
    modules: list[str] = []
    current: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if current:
            body = "\n".join(buf)
            els: dict[str, str] = {}
            for line in buf:
                m = ELEMENT_RE.match(line)
                if m:
                    lbl = m.group("label").strip()
                    if lbl not in els:
                        els[lbl] = m.group("value").strip()
            if current in sections:
                # 同名标题重复出现（例如补丁文件把标题复制了两次）：合并而不是覆盖，
                # 保留先出现的内容，防止后段把整条答案冲掉。
                prev = sections[current]
                for k, v in els.items():
                    prev["elements"].setdefault(k, v)
                prev["block"] = prev["block"] + "\n" + body
            else:
                sections[current] = {"elements": els, "block": body}

    for line in text.splitlines():
        m_item = ITEM_HEAD_RE.match(line)
        if m_item:
            flush()
            current = m_item.group("id").upper()
            buf = []
            continue
        m_mod = MODULE_HEAD_RE.match(line)
        if m_mod and not m_item:
            modules.append(m_mod.group("title").strip())
        if current is not None:
            buf.append(line)
    flush()
    return sections, modules


def judge_value(value: str, expect: str, block: str, block_has_table: bool) -> tuple[bool, str]:
    """判定单个原子核对项是否合格。返回 (ok, 原因)。"""
    v = value.strip()
    if not v:
        return False, "空值"
    if not v.replace(PLACEHOLDER, "").strip() or PLACEHOLDER in v:
        return False, "未作答占位（不是答案）"

    is_gap = bool(GAP_RE.search(v))
    if is_gap:
        if GAP_SHORT_OK.match(v):
            return True, "缺口声明"
        if len(v) < 8:
            return False, "缺口声明过短，必须写清取数路径"
        if not PATH_HINT_RE.search(v):
            return False, "缺口声明未给取数路径"
        return True, "缺口声明+路径"

    if expect == "number":
        if not DIGIT_RE.search(v):
            return False, "问数字但答案中没有数字，也未声明缺口"
    elif expect == "table":
        if "|" not in v and not block_has_table:
            return False, "要求表格，但既无表格也未声明缺口"
    elif expect == "list":
        if len(v) < 4:
            return False, "列表内容过短"
    elif expect == "text":
        if len(v) < 15:
            return False, "论述过短（<15 字），疑似敷衍"
    elif expect == "conclusion":
        if len(v) < 10:
            return False, "结论过短（<10 字）"
    elif expect == "evidence":
        if not SOURCE_RE.search(v):
            return False, "要求可回溯来源，但未见公告名/编号/日期/链接"

    if FILLER_RE.search(v) and not DIGIT_RE.search(v) and not SOURCE_RE.search(v):
        return False, "只有套话没有数字和来源"
    return True, "ok"


def has_table(text: str) -> bool:
    rows = [ln for ln in text.splitlines() if ln.count("|") >= 2]
    return len(rows) >= 3


def table_data_rows(text: str) -> int:
    rows = [ln for ln in text.splitlines() if ln.count("|") >= 2]
    return len([r for r in rows if not re.fullmatch(r"[\s|:\-]+", r)])


def main() -> int:
    ap = argparse.ArgumentParser(description="覆盖率硬闸门")
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=None, help="默认 <run>/report.md")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args()

    run_dir = args.run.expanduser().resolve()
    bank = json.loads((run_dir / "bank.json").read_text(encoding="utf-8"))
    report_path = args.report or (run_dir / "report.md")
    if not report_path.exists():
        raise SystemExit(f"报告不存在，先跑 assemble_report.py: {report_path}")

    report = report_path.read_text(encoding="utf-8")
    sections, modules = parse_report(report)

    rows: list[dict] = []
    failures: list[str] = []

    # 1) 模块齐全
    for m in bank["modules"]:
        if not any(m["title"] in t for t in modules):
            failures.append(f"[模块缺失] {m['id']} {m['title']} 在报告里找不到标题")

    total_items = 0
    ok_items = 0
    total_els = 0
    ok_els = 0

    # 2) 逐节点、逐原子核对项
    for m in bank["modules"]:
        for item in m["items"]:
            total_items += 1
            sec = sections.get(item["id"])
            problems: list[str] = []
            filled = 0
            placeholders = 0

            if sec is None:
                problems.append("整条节点缺失")
                block = ""
                els: dict[str, str] = {}
            else:
                block = sec["block"]
                els = sec["elements"]
                if len(block) < MIN_BLOCK_CHARS:
                    problems.append(f"区块过短（{len(block)} 字），疑似敷衍")
                if "（缺口：未作答）" in block:
                    problems.append("存在未作答占位")

            block_table = has_table(block) if sec else False

            for el in item["elements"]:
                total_els += 1
                val = els.get(el["label"])
                if val is None:
                    problems.append(f"缺核对项：{el['label']}")
                    continue
                if PLACEHOLDER in val:
                    placeholders += 1
                ok, why = judge_value(val, el["expect"], block, block_table)
                if ok:
                    filled += 1
                    ok_els += 1
                else:
                    problems.append(f"{el['label']}：{why}")

            status = "PASS" if not problems else "FAIL"
            if status == "PASS":
                ok_items += 1
            else:
                failures.append(f"[{item['id']}] {item['ask']}\n      - " + "\n      - ".join(problems))

            rows.append({
                "节点": item["id"],
                "模块": f"{m['id']} {m['title']}",
                "核对项总数": len(item["elements"]),
                "已合格": filled,
                "占位符": placeholders,
                "状态": status,
                "问题": "；".join(problems),
            })

    # 3) 汇总表（粒度由题库的 rubric 决定）
    rubric = bank.get("rubric", {})
    rb_id = rubric.get("id", "RB")
    rb_title = rubric.get("title", "汇总表")
    rb_dims = rubric.get("dimensions", [])
    rb_extras = rubric.get("extra_required", [])
    min_rows = rubric.get("min_rows") or DEFAULT_RUBRIC_MIN_ROWS
    rb_sec = sections.get(rb_id.upper())
    rb_problems: list[str] = []
    rb_extra_filled = 0
    table_ok = False
    rb_block = ""
    if rb_sec is None:
        rb_problems.append("整张汇总表缺失")
    else:
        rb_block = rb_sec["block"]
        rows_n = table_data_rows(rb_block)
        if rows_n < min_rows:
            rb_problems.append(f"表格行数不足（{rows_n} < {min_rows}，需表头+{len(rb_dims)} 行）")
        else:
            table_ok = True
        if "（缺口：未作答）" in rb_block:
            rb_problems.append("存在未作答占位")
            table_ok = False
        for e in rb_extras:
            val = rb_sec["elements"].get(e["label"])
            if val is None:
                rb_problems.append(f"缺核对项：{e['label']}")
                continue
            ok, why = judge_value(val, e.get("expect", "text"), rb_block, has_table(rb_block))
            if ok:
                rb_extra_filled += 1
            else:
                rb_problems.append(f"{e['label']}：{why}")
    if rb_problems:
        failures.append(f"[{rb_id}] {rb_title}：" + "；".join(rb_problems))
    rows.append({
        "节点": rb_id,
        "模块": rb_title,
        "核对项总数": len(rb_dims) + len(rb_extras),
        "已合格": (len(rb_dims) if table_ok else 0) + rb_extra_filled,
        "占位符": len(rb_dims) + len(rb_extras) if "（缺口：未作答）" in rb_block else 0,
        "状态": "PASS" if not rb_problems else "FAIL",
        "问题": "；".join(rb_problems),
    })

    # 4) 结论输出
    total_els_all = total_els + len(rb_dims) + len(rb_extras)
    ok_els_all = ok_els + (len(rb_dims) if table_ok else 0) + rb_extra_filled
    passed = not failures
    rate = ok_els_all / total_els_all * 100 if total_els_all else 0.0

    out_path = args.out or (run_dir / "coverage_report.md")
    csv_path = args.csv or (run_dir / "coverage.csv")

    lines: list[str] = []
    lines.append("# 覆盖率核查报告")
    lines.append("")
    lines.append(f"- 报告文件：`{report_path}`")
    lines.append(f"- 分母：**{total_items} 个节点 / {total_els_all} 条必答内容**"
                 f"（含汇总表 {len(rb_dims)} 行 + {len(rb_extras)} 个汇总核对项）")
    lines.append(f"- 合格节点：**{ok_items}/{total_items}**")
    lines.append(f"- 合格核对项：**{ok_els_all}/{total_els_all}（{rate:.1f}%）**")
    lines.append(f"- 闸门结果：**{'通过（exit 0）' if passed else '不通过（exit 1）'}**")
    lines.append("")
    if failures:
        lines.append(f"## 不合格清单（{len(failures)} 条）")
        lines.append("")
        for i, f in enumerate(failures, 1):
            lines.append(f"{i}. {f}")
        lines.append("")
        lines.append("## 补漏方式")
        lines.append("")
        lines.append("对上面每个不合格节点，把重写后的完整区块写进 `<run>/blocks/<节点ID>.md`"
                     "（格式：`### [节点ID] 原文标题` + 逐行 `**核对项**：答案`），"
                     "然后重跑 `assemble_report.py` 与本脚本。")
    else:
        lines.append("全部节点与原子核对项均已点对点作答，可以交付。")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["节点", "模块", "核对项总数", "已合格", "占位符", "状态", "问题"])
        w.writeheader()
        w.writerows(rows)

    print(f"覆盖率核查：节点 {ok_items}/{total_items}，核对项 {ok_els_all}/{total_els_all}（{rate:.1f}%）")
    print(f"已写 {out_path}")
    print(f"已写 {csv_path}")
    if passed:
        print("gate exit=0 可交付")
        return 0
    print(f"gate exit=1 不合格 {len(failures)} 条，必须补漏后重跑")
    return 1


if __name__ == "__main__":
    sys.exit(main())
