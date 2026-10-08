#!/usr/bin/env python3
"""建一次分析运行目录：冻结题库 + 写各模块作答提纲 + 生成 workflow 参数。

用法：
    python3 build_run.py --ticker 600519 --name 贵州茅台 --market A股 \
        --as-of 2026-10-06 --out ~/Desktop/quant流量/fundamental_runs/20261006_600519

产物（全部落在 --out 目录）：
    bank.json            本次冻结的题库副本（覆盖率分母，之后不再变）
    meta.json            标的/市场/基准日
    prompts/M*.md        每个模块的作答提纲（含必须逐行回答的原子核对项清单）
    CHECKLIST.md         给人看的核对清单
    workflow_args.json   直接喂给 workflow 工具的 args
    parts/ blocks/       作答区与补漏区
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BANK = HERE / "question_bank.json"
DEFAULT_CONTRACT = HERE.parent / "references" / "answer_contract.md"

MARKET_ALIASES = {
    "a": "A股", "a股": "A股", "sh": "A股", "sz": "A股",
    "hk": "港股", "港股": "港股",
    "us": "美股", "美股": "美股",
}


def normalize_market(raw: str | None) -> str:
    if not raw:
        return "A股"
    return MARKET_ALIASES.get(raw.strip().lower(), raw.strip())


def infer_market(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.isdigit() and len(t) == 6:
        return "A股"
    if t.isdigit() and len(t) == 5:
        return "港股"
    return "美股"


def render_prompt(meta: dict, module: dict, bank: dict) -> str:
    lines: list[str] = []
    lines.append(f"# 作答提纲 · {module['id']} {module['title']}")
    lines.append("")
    lines.append(f"- 标的：**{meta['name']}（{meta['ticker']}）**　市场：{meta['market']}　数据基准日：**{meta['as_of']}**")
    lines.append(f"- 本模块共 {len(module['items'])} 个节点，节点下共 "
                 f"{sum(len(i['elements']) for i in module['items'])} 个原子核对项。")
    lines.append("")
    lines.append("## 硬性产出要求")
    lines.append("")
    lines.append("1. 用 write 工具把结果写到指定文件（见文末路径）。")
    lines.append("2. 每个节点一个区块，区块标题必须是 `### [节点ID] 原图原文`（ID 与标题严格照抄本文件）。")
    lines.append("3. 节点下**每个原子核对项必须单独占一行**，格式：`**<核对项名称>**：<答案>`。")
    lines.append("   核对项名称必须与下面列出的**完全一致**，一行一个，"
                 "**禁止合并、禁止省略、禁止改写名称**。")
    lines.append("4. 数字一律带来源（公告名/编号+日期，或投关/业绩说明会原文，或数据机构+链接）。")
    lines.append("   查不到就写 `未披露` / `未能获取`，并给出**取数路径**（去哪个文件、哪个栏目查）。")
    lines.append("   缺口声明是合格答案；编造和含糊其辞不是。")
    lines.append("5. 允许联网检索（web_search / web_fetch）。优先公司公告、投资者关系记录、业绩说明会、"
                 "年报/半年报/季报原文，其次权威数据源。")
    lines.append("6. 需要展开的分析写在核对项之后，用 `#### 分析` 起头；不得用它替代任何核对项。")
    lines.append("")
    lines.append(f"> 完整契约见：`{meta['contract_path']}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    for item in module["items"]:
        lines.append(f"### [{item['id']}] {item['source_text']}")
        if item.get("needs_input"):
            lines.append("")
            lines.append("> ⚠️ 原图此节点含未填写占位（xxx）。**不得替用户猜**："
                         "必须在『待补输入』一行写明缺什么，其余按通用框架作答。")
        lines.append("")
        lines.append(f"**问的是**：{item['ask']}")
        lines.append("")
        lines.append("**必须逐行回答的原子核对项**：")
        for el in item["elements"]:
            hint = f"（{el['hint']}）" if el.get("hint") else ""
            lines.append(f"- `{el['label']}`　（类型 {el['expect']}，仅供你参考，勿抄进答案）{hint}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 产出文件")
    lines.append("")
    lines.append(f"把上述内容写进：`{meta['run_dir']}/parts/{module['id']}.md`")
    lines.append("")
    lines.append(f"（题库唯一事实来源：`{meta['run_dir']}/bank.json`，可读但不要改。）")
    lines.append("")
    return "\n".join(lines)


def render_rubric_prompt(meta: dict, bank: dict) -> str:
    """总表（rubric）的作答提纲：只能汇总已有正文，不得引入新数字。"""
    rb = bank["rubric"]
    lines = [f"# 作答提纲 · [{rb['id']}] {rb['title']}", ""]
    lines.append(f"- 标的：**{meta['name']}（{meta['ticker']}）**　基准日：**{meta['as_of']}**")
    lines.append("")
    lines.append("## 要求")
    lines.append("")
    lines.append("1. 先读完各模块已完成的作答文件（" +
                 "、".join(f"`{meta['run_dir']}/parts/{m['id']}.md`" for m in bank["modules"]) +
                 "），**只能基于它们已经写下的结论与证据**汇总，不得新引入未在正文出现的数字。")
    lines.append(f"2. 输出一张 Markdown 表格，列固定为：{' | '.join(rb.get('columns') or ['维度', '判定标准', '实际数据', '结论'])}，"
                 f"每个维度一行（含表头至少 {rb.get('min_rows', 10)} 行）。")
    lines.append("3. 表格之后，再逐行给出下列核对项，格式 `**<核对项名称>**：<答案>`：")
    for e in rb.get("extra_required", []) or []:
        hint = f"（{e['hint']}）" if e.get("hint") else ""
        lines.append(f"   - `{e['label']}`　（类型 {e.get('expect', 'text')}，仅供你参考，勿抄进答案）{hint}")
    lines.append("")
    lines.append(f"4. 用 write 工具写入：`{meta['run_dir']}/parts/{rb['id']}.md`，"
                 f"首行必须是与文件名一致的标题行：`### [{rb['id']}] {rb['title']}`")
    lines.append("")
    return "\n".join(lines)


def render_checklist(meta: dict, bank: dict) -> str:
    lines = [f"# 核对清单 · {meta['name']}（{meta['ticker']}）", ""]
    lines.append(f"- 市场：{meta['market']}　基准日：{meta['as_of']}　题库：{bank['bank_name']}")
    total_items = sum(len(m["items"]) for m in bank["modules"])
    total_els = sum(len(i["elements"]) for m in bank["modules"] for i in m["items"])
    lines.append(f"- 分母：**{total_items} 个节点 / {total_els} 个原子核对项**")
    lines.append("")
    for m in bank["modules"]:
        lines.append(f"## {m['id']} {m['title']}")
        for item in m["items"]:
            flag = " ⚠需补输入" if item.get("needs_input") else ""
            lines.append(f"- [ ] **[{item['id']}]**{flag} {item['ask']}")
            for el in item["elements"]:
                lines.append(f"    - [ ] {el['label']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="建一次基本面全覆盖分析运行目录")
    ap.add_argument("--ticker", required=True, help="股票代码，如 600519 / 00700 / NVDA")
    ap.add_argument("--name", default="", help="公司名，如 贵州茅台")
    ap.add_argument("--market", default=None, help="A股/港股/美股；省略则按代码推断")
    ap.add_argument("--as-of", default=None, help="数据基准日 YYYY-MM-DD；默认今天")
    ap.add_argument("--out", type=Path, required=True, help="运行目录")
    ap.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = ap.parse_args()

    if not args.bank.exists():
        raise SystemExit(f"题库不存在: {args.bank}")
    bank = json.loads(args.bank.read_text(encoding="utf-8"))

    ticker = args.ticker.strip()
    market = normalize_market(args.market) if args.market else infer_market(ticker)
    as_of = args.as_of or datetime.now().strftime("%Y-%m-%d")
    name = args.name.strip() or ticker

    run_dir = args.out.expanduser().resolve()
    (run_dir / "parts").mkdir(parents=True, exist_ok=True)
    (run_dir / "blocks").mkdir(parents=True, exist_ok=True)
    (run_dir / "prompts").mkdir(parents=True, exist_ok=True)

    shutil.copyfile(args.bank, run_dir / "bank.json")

    meta = {
        "ticker": ticker,
        "name": name,
        "market": market,
        "as_of": as_of,
        "run_dir": str(run_dir),
        "bank_path": str(run_dir / "bank.json"),
        "bank_source": str(args.bank),
        "bank_sha256_source": bank["source"]["sha256"],
        "contract_path": str(args.contract),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "CHECKLIST.md").write_text(render_checklist(meta, bank), encoding="utf-8")

    rb = bank["rubric"]
    rb_prompt = run_dir / "prompts" / f"{rb['id']}.md"
    rb_prompt.write_text(render_rubric_prompt(meta, bank), encoding="utf-8")

    modules_out = []
    for m in bank["modules"]:
        prompt_path = run_dir / "prompts" / f"{m['id']}.md"
        prompt_path.write_text(render_prompt(meta, m, bank), encoding="utf-8")
        modules_out.append({
            "id": m["id"],
            "title": m["title"],
            "prompt_path": str(prompt_path),
            "part_path": str(run_dir / "parts" / f"{m['id']}.md"),
            "item_ids": [i["id"] for i in m["items"]],
            "element_count": sum(len(i["elements"]) for i in m["items"]),
        })

    wf_args = {
        "run_dir": str(run_dir),
        "bank_path": str(run_dir / "bank.json"),
        "contract_path": str(args.contract),
        "meta": meta,
        "modules": modules_out,
        "rubric": {
            "id": rb["id"],
            "title": rb["title"],
            "prompt_path": str(rb_prompt),
            "part_path": str(run_dir / "parts" / f"{rb['id']}.md"),
        },
    }
    (run_dir / "workflow_args.json").write_text(
        json.dumps(wf_args, ensure_ascii=False, indent=2), encoding="utf-8")

    total_items = sum(len(m["items"]) for m in bank["modules"])
    total_els = sum(m["element_count"] for m in modules_out)
    print(f"运行目录: {run_dir}")
    print(f"标的: {name}（{ticker}）  市场: {market}  基准日: {as_of}")
    print(f"分母: {total_items} 个节点 / {total_els} 个原子核对项，切成 {len(modules_out)} 个模块")
    for m in modules_out:
        print(f"  {m['id']} {m['title']}: {len(m['item_ids'])} 节点 / {m['element_count']} 核对项 → {Path(m['part_path']).name}")
    print(f"  {rb['id']} {rb['title']}: {len(rb['dimensions'])} 行"
          f" + {len(rb.get('extra_required', []))} 个汇总核对项")
    print(f"workflow 参数: {run_dir / 'workflow_args.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
