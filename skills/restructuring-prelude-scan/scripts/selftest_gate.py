#!/usr/bin/env python3
"""「重组前戏信号排查」覆盖率闸门的自测基线：10 个对抗用例。

用法：
    python3 selftest_gate.py            # 临时目录里跑，用完即删
    python3 selftest_gate.py --keep     # 保留产物便于排查

判定（任一不满足即退出码 1）：
  1  完整作答                     → exit 0
  2  吞掉整条信号节点             → exit 1
  3  合并两个核对项               → exit 1
  4  空话套话                     → exit 1
  5  数字题只给定性               → exit 1
  6  证据题无来源                 → exit 1
  7  缺口声明过短                 → exit 1
  8  汇总表缺失                   → exit 1
  9  结论过短                     → exit 1
 10  合法缺口(未披露+取数路径)     → exit 0
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build_run.py"
ASSEMBLE = HERE / "assemble_report.py"
CHECK = HERE / "coverage_check.py"
BANK = HERE / "question_bank.json"

CONC = "出现，依据为 2025-08-28 公告（依据等级 A），与本次信号高度相关。"
LIST = "中金公司（财务顾问）；某某律师事务所"
TEXT = "检索了巨潮资讯网与互动易，窗口内关键词为重组、收购、停牌。"
EVID = "2025 年半年报，公告编号 2025-058"
NUM = "123.4 亿元（来源：2025 年半年报，2025-08-28）"


def ok_value(el: dict) -> str:
    exp = el["expect"]
    if exp == "number":
        return NUM
    if exp == "table":
        return "见下方表格 | 指标 | Q1 | Q2 | Q3 |"
    if exp == "list":
        return LIST
    if exp == "evidence":
        return EVID
    if exp == "text":
        return TEXT
    if exp == "conclusion":
        return CONC
    return "已作答"


def make_ok_run(root: Path, bank: dict) -> Path:
    run = root / "run_ok"
    subprocess.run(
        [sys.executable, str(BUILD), "--ticker", "300750", "--name", "示例公司",
         "--market", "A股", "--as-of", "2026-10-06", "--out", str(run)],
        check=True, capture_output=True, text=True,
    )
    for m in bank["modules"]:
        lines = [f"# {m['id']} {m['title']}", ""]
        for it in m["items"]:
            lines.append(f"### [{it['id']}] {it['source_text']}")
            lines.append("")
            for el in it["elements"]:
                lines.append(f"**{el['label']}**：{ok_value(el)}")
            lines.append("")
            lines.append("#### 分析")
            lines.append("")
            lines.append("本条基于公开披露与可回溯来源逐项核对后给出判断，" * 3)
            lines.append("")
        (run / "parts" / f"{m['id']}.md").write_text("\n".join(lines), encoding="utf-8")

    rb = bank["rubric"]
    cols = rb.get("columns") or ["维度", "判定标准", "实际数据", "结论"]
    t = [f"### [{rb['id']}] {rb['title']}", "",
         "| " + " | ".join(cols) + " |",
         "| " + " | ".join("---" for _ in cols) + " |"]
    for d in rb["dimensions"]:
        t.append("| " + " | ".join([d["label"]] + ["出现，A 级证据"] * (len(cols) - 1)) + " |")
    t.append("")
    for e in rb.get("extra_required", []):
        exp = e.get("expect", "text")
        if exp == "list":
            val = "R03 清壳（2025-03）、R05 现金授信突增（2025-06）、R09 控股股东变更（2025-09）"
        elif exp == "conclusion":
            val = "处于重组前戏，把握度 65%（依据 3 条 A 级信号聚集于近 6 个月）。"
        else:
            val = "以上结论含 D 级推断成分，仅作线索排查，不构成投资依据。"
        t.append(f"**{e['label']}**：{val}")
    (run / "parts" / f"{rb['id']}.md").write_text("\n".join(t) + "\n", encoding="utf-8")
    return run


def edit(path: Path, fn) -> None:
    t = path.read_text(encoding="utf-8")
    path.write_text(fn(t), encoding="utf-8")


def mutate_swallow_node(run: Path) -> None:
    edit(run / "parts" / "M4.md",
         lambda t: re.sub(r"### \[R12\].*?(?=\Z)", "", t, flags=re.S))


def mutate_merge_elements(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**是否出现**：{CONC}\n**中介机构与类型**：{LIST}",
        "**是否出现**：出现，且已公告聘请中金公司担任财务顾问，指向资本运作。",
    ))


def mutate_filler(run: Path) -> None:
    edit(run / "parts" / "M2.md", lambda t: t.replace(
        f"**提前还贷金额**：{NUM}",
        "**提前还贷金额**：综合来看整体表现良好，值得持续关注。",
    ))


def mutate_number_handwave(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**增资金额与估值**：{NUM}",
        "**增资金额与估值**：增资金额较大，估值较前期有所提升。",
    ))


def mutate_no_source(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**公告日期与编号**：{EVID}",
        "**公告日期与编号**：根据公开信息整理。",
    ))


def mutate_short_gap(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**取数路径**：{TEXT}", "**取数路径**：未披露。"))


def mutate_no_rubric(run: Path) -> None:
    (run / "parts" / "RB.md").unlink()


def mutate_short_conclusion(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**是否出现**：{CONC}", "**是否出现**：出现。"))


def mutate_legit_gap(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        f"**取数路径**：{TEXT}",
        "**取数路径**：未披露。取数路径：窗口内巨潮资讯网无相关公告；"
        "可于公司公告栏以关键词「财务顾问」「重大资产重组」检索，"
        "或查阅最近一期投资者关系活动记录表。",
    ))


def check_invariant(run: Path) -> list[str]:
    """不变量：凡是"整条节点缺失"的节点，其"已合格"必须是 0。

    这条断言专门防住一类隐蔽 bug：装配层的占位符 `（缺口：未作答）` 长度 8，
    曾能通过 list 类的长度校验，导致合格数虚高（退码不变，肉眼看不出来）。
    """
    csv_path = run / "coverage.csv"
    if not csv_path.exists():
        return [f"{run.name}: 未生成 coverage.csv"]
    bad: list[str] = []
    with csv_path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            # 不变量：占位符一个都不能算合格 —— 即 已合格 + 占位符 <= 核对项总数。
            # 装配占位符 `（缺口：未作答）` 长达 8 字，曾能骗过 list 类的长度校验，
            # 导致合格数虚高（退出码不变，只有这一列看得出来）。
            try:
                filled = int(row["已合格"]); total = int(row["核对项总数"])
                ph = int(row.get("占位符", 0) or 0)
            except (KeyError, ValueError):
                bad.append(f"{row['节点']} 覆盖率 CSV 缺列或数值异常")
                continue
            if filled + ph > total:
                bad.append(f"{row['节点']} 占位符被算作合格（合格 {filled} + 占位 {ph} > 总数 {total}）")
    return bad


CASES = [
    ("完整作答", None, 0),
    ("吞掉整条信号节点", mutate_swallow_node, 1),
    ("合并两个核对项", mutate_merge_elements, 1),
    ("空话套话", mutate_filler, 1),
    ("数字题只给定性", mutate_number_handwave, 1),
    ("证据题无来源", mutate_no_source, 1),
    ("缺口声明过短", mutate_short_gap, 1),
    ("汇总表缺失", mutate_no_rubric, 1),
    ("结论过短", mutate_short_conclusion, 1),
    ("合法缺口应放行", mutate_legit_gap, 0),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留临时产物")
    args = ap.parse_args()

    bank = json.loads(BANK.read_text(encoding="utf-8"))
    root = Path(tempfile.mkdtemp(prefix="restructuring_selftest_"))
    try:
        base = make_ok_run(root, bank)
        print(f"{'用例':<20} {'期望':<6} {'实际':<6} 判定")
        print("-" * 60)
        bad: list[str] = []
        for name, mut, expect in CASES:
            run = root / re.sub(r"[^\w]", "_", name)
            shutil.copytree(base, run)
            if mut:
                mut(run)
            subprocess.run([sys.executable, str(ASSEMBLE), "--run", str(run)],
                           capture_output=True, text=True)
            rc = subprocess.run([sys.executable, str(CHECK), "--run", str(run)],
                                capture_output=True, text=True).returncode
            viol = check_invariant(run)
            ok = (rc == expect) and not viol
            verdict = "✅" if ok else ("❌ 退码不符" if rc != expect else "❌ 指标虚高")
            if not ok:
                bad.append(name)
            print(f"{name:<20} exit={expect:<3} exit={rc:<3} {verdict}"
                  + (f"  [{'; '.join(viol)}]" if viol else ""))
        print("-" * 60)
        if bad:
            print(f"失败用例：{', '.join(bad)}")
            return 1
        print("自测基线全部通过：闸门既不漏放行，也不误杀合法缺口。")
        return 0
    finally:
        if args.keep:
            print(f"产物保留在：{root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
