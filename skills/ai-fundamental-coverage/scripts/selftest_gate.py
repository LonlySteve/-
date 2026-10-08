#!/usr/bin/env python3
"""覆盖率闸门的自测基线：9 个对抗用例，验证闸门既不漏放行、也不误杀。

用法：
    python3 selftest_gate.py            # 在临时目录里跑，用完即删
    python3 selftest_gate.py --keep     # 保留产物便于排查

判定（任一不满足即退出码 1）：
  1 完整作答                 → exit 0
  2 吞掉整条节点             → exit 1
  3 合并两个核对项           → exit 1
  4 空话套话                 → exit 1
  5 数字题只给定性           → exit 1
  6 证据题无来源             → exit 1
  7 缺口声明过短             → exit 1
  8 造血评分表缺失           → exit 1
  9 表格题不造表             → exit 1
 10 合法缺口(未披露+取数路径) → exit 0
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


def ok_value(el: dict) -> str:
    exp = el["expect"]
    if exp == "number":
        return "123.4 亿元（来源：2025 年半年报，2025-08-28）"
    if exp == "table":
        return "见下方表格 | 指标 | Q1 | Q2 | Q3 |"
    if exp == "list":
        return "预付款比例 30% ；违约金条款；最低采购量承诺"
    if exp == "evidence":
        return "2025 年半年报，公告编号 2025-058"
    if exp == "text":
        return "按季度跟踪该指标，数据来源为公司定期报告与投资者关系活动记录表。"
    if exp == "conclusion":
        return "结论：具备头部地位，依据为专利数量与客户层级均领先可比公司。"
    return "已作答"


def make_ok_run(root: Path, bank: dict) -> Path:
    run = root / "run_ok"
    subprocess.run(
        [sys.executable, str(BUILD), "--ticker", "600519", "--name", "贵州茅台",
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
            lines.append("本次分析基于公司定期报告与公开公告，逐项核对后给出上述判断，" * 3)
            lines.append("")
        (run / "parts" / f"{m['id']}.md").write_text("\n".join(lines), encoding="utf-8")

    rb = bank["rubric"]
    t = ["### [RB] 公司自身造血能力 · 评分维度表", "",
         "| 维度 | 判定标准 | 实际数据 | 结论 |", "| --- | --- | --- | --- |"]
    for d in rb["dimensions"]:
        t.append(f"| {d['label']} | {d['criterion']} | 2025Q3 为 12.3 亿元 | 改善 |")
    (run / "parts" / "M5_rubric.md").write_text("\n".join(t) + "\n", encoding="utf-8")
    return run


def edit(path: Path, fn) -> None:
    t = path.read_text(encoding="utf-8")
    path.write_text(fn(t), encoding="utf-8")


def mutate_swallow_node(run: Path) -> None:
    edit(run / "parts" / "M3.md", lambda t: re.sub(r"### \[F11\].*?(?=\Z)", "", t, flags=re.S))


def mutate_merge_elements(run: Path) -> None:
    edit(run / "parts" / "M1.md", lambda t: t.replace(
        "**在手订单金额**：123.4 亿元（来源：2025 年半年报，2025-08-28）\n"
        "**在手订单同比变化**：123.4 亿元（来源：2025 年半年报，2025-08-28）",
        "**在手订单金额**：123.4 亿元，同比变化也在其中（来源：2025 年半年报，2025-08-28）",
    ))


def mutate_filler(run: Path) -> None:
    edit(run / "parts" / "M2.md", lambda t: t.replace(
        "**专利数量**：123.4 亿元（来源：2025 年半年报，2025-08-28）",
        "**专利数量**：综合来看整体表现良好，值得关注。",
    ))


def mutate_number_handwave(run: Path) -> None:
    edit(run / "parts" / "M5.md", lambda t: t.replace(
        "**单季经营活动现金流净额**：123.4 亿元（来源：2025 年半年报，2025-08-28）",
        "**单季经营活动现金流净额**：现金流较上年同期大幅改善，趋势向好。",
    ))


def mutate_no_source(run: Path) -> None:
    edit(run / "parts" / "M3.md", lambda t: t.replace(
        "**公告来源**：2025 年半年报，公告编号 2025-058",
        "**公告来源**：根据公开信息整理。",
    ))


def mutate_short_gap(run: Path) -> None:
    edit(run / "parts" / "M4.md", lambda t: t.replace(
        "**最新持股比例**：123.4 亿元（来源：2025 年半年报，2025-08-28）",
        "**最新持股比例**：未披露。",
    ))


def mutate_no_rubric(run: Path) -> None:
    (run / "parts" / "M5_rubric.md").unlink()


def mutate_no_table(run: Path) -> None:
    edit(run / "parts" / "M5.md", lambda t: t.replace(
        "**指标表格**：见下方表格 | 指标 | Q1 | Q2 | Q3 |",
        "**指标表格**：数据已在上面各条列出。",
    ))


def mutate_legit_gap(run: Path) -> None:
    edit(run / "parts" / "M4.md", lambda t: t.replace(
        "**最新持股比例**：123.4 亿元（来源：2025 年半年报，2025-08-28）",
        "**最新持股比例**：未披露。取数路径：查公司 2025 年半年报"
        "「合并范围变更」与「在其他主体中的权益」附注。",
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
    ("吞掉整条节点", mutate_swallow_node, 1),
    ("合并两个核对项", mutate_merge_elements, 1),
    ("空话套话", mutate_filler, 1),
    ("数字题只给定性", mutate_number_handwave, 1),
    ("证据题无来源", mutate_no_source, 1),
    ("缺口声明过短", mutate_short_gap, 1),
    ("造血评分表缺失", mutate_no_rubric, 1),
    ("表格题不造表", mutate_no_table, 1),
    ("合法缺口应放行", mutate_legit_gap, 0),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留临时产物")
    args = ap.parse_args()

    bank = json.loads(BANK.read_text(encoding="utf-8"))
    root = Path(tempfile.mkdtemp(prefix="coverage_selftest_"))
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
