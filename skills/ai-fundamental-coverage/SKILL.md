---
name: ai-fundamental-coverage
description: 对任意一只股票做"滴水不漏"的逐条基本面排查。当用户说"分析/排查某只股票的基本面"、"AI咨询基本面偏"、"逐条回答这些基本面问题"、"点对点分析"，或抱怨 agent 又把某些问题跳过/合并/糊过去时，加载本技能。题库已固化（8 模块 / 20 节点 / 95 个原子核对项），只需给出股票代码与基准日，并用确定性覆盖率闸门保证一条不漏。
argument-hint: 股票代码（如 600519 / 00700 / NVDA），可附公司名与数据基准日
---

# AI咨询基本面偏 · 逐节点全覆盖排查

**题库已固化在本技能里，不需要用户再提供思维导图。** 用户只要说"查 XXX 基本面"，就按本流程跑完。

- 题库（唯一事实来源）：`scripts/question_bank.json` —— 8 模块 / **20 个必答节点 / 95 个原子核对项**
- 回答契约（作答与审计共同判据）：`references/answer_contract.md`
- 题库来源：`AI咨询基本面偏.emmx`（中心主题树 28 节点中，8 个 MainTopic 为分类标题不计分母；其余 20 个节点逐条作答，含 `产能 和收入 若无请明示`、`供应链弹性 check` 两个非疑问句）
- 浮动主题「公司自身造血能力」= M5 自身造血分支的**判据展开**，作为评分维度表随 M5 交付，不单独计入分母
- 浮动主题「催化事件时间线 / 重组前戏 / AIPDF搜索 / AI系列」**不在本次范围**，不要答

---

## 0. 先确认三件事（缺就一次问全，不要猜）

1. **股票代码**（必填）
2. **数据基准日**（默认今天）
3. 公司名（可选，用于检索；不给就按代码推断）

市场（A股/港股/美股）可由代码推断，不必问。

---

## 1. 建运行目录（不可跳过）

```bash
RUN="$PWD/fundamental_runs/$(date +%Y%m%d)_<代码>"
python3 ~/.agents/skills/ai-fundamental-coverage/scripts/build_run.py \
    --ticker "<代码>" --name "<公司名>" --market "<A股|港股|美股>" \
    --as-of "<基准日>" --out "$RUN"
```

产物：`bank.json`（本次冻结的题库）、`meta.json`、`prompts/M*.md`（各模块作答提纲，内含必须逐行回答的核对项清单）、`prompts/RB.md`（造血评分总表提纲）、`CHECKLIST.md`、`workflow_args.json`、`parts/`、`blocks/`。

脚本会打印分母：**20 个节点 / 95 个原子核对项**。把它记下来，后面所有"覆盖完了"的说法都要由这个数字背书。

---

## 2. 跑编排（首选路径）

读 `workflows/coverage_run.js` 的**全文**作为 `workflow` 工具的 `script`，把 `$RUN/workflow_args.json` 的内容作为 `args` 传入。

脚本内部：

1. **逐模块并行作答**（8 个 agent，各自读 `prompts/M*.md`，写到 `parts/M*.md`）；
2. **独立审计**（换一个 agent，只挑错，不写内容，逐核对项判 ok/partial/missing）；
3. **定点补漏**（只重写不合格节点，写 `blocks/<节点ID>.md`，补丁优先于 parts）并立刻复核；
4. **汇总总表**（读全部已完成 parts，生成 `parts/RB.md` 造血评分维度表；**不得引入正文没有的新数字**）；
5. **装配自检**，返回紧凑状态。

> 总表由 agent 产出、不自动生成——跳过第 4 步，闸门会报「汇总表缺失」。

规模参考：8 个模块 ≈ 20–30 个 agent 调用，约 15–30 分钟。正文全部落盘，不会撑爆上下文。

### 降级路径（没有 `workflow` 工具时）

- 用 `subagent`：每个模块一个子 agent，prompt 里给 `prompts/M*.md` 的路径 + 契约路径 + "写入 `parts/M*.md`"的要求；再各起一个审计 subagent；再对不合格节点起补漏 subagent。
- 什么都没有时：**自己在当前会话里逐模块写 `parts/M*.md`**，写一个模块立刻自检一个模块。绝不要"一口气把 95 项都答了"——那正是漏答的根源。

---

## 3. 装配

```bash
python3 ~/.agents/skills/ai-fundamental-coverage/scripts/assemble_report.py --run "$RUN"
```

标题、顺序、核对项清单全由 `bank.json` 决定，模型只提供正文；缺片段会写成显式 `（缺口：未作答）`，绝不静默吞掉。

---

## 4. 硬闸门（决定能不能交付）

```bash
python3 ~/.agents/skills/ai-fundamental-coverage/scripts/coverage_check.py --run "$RUN"
echo "gate exit=$?"
```

逐节点、逐原子核对项独立核对 `report.md`：
区块是否存在、核对项是否**逐行且名称一致**、问数字的有没有数字、要求表格的有没有真表格、要求来源的能不能回溯、缺口声明是否写了取数路径、有没有用套话覆盖多项。

- **退出码 0 才能交付。**
- 退出码 1：拿 `coverage_report.md` 的"不合格清单"，起补漏 agent 写 `blocks/<节点ID>.md`，**重跑第 3、4 步**，循环到 0（通常 1–2 轮）。

自测基线（**改动 `scripts/` 下任何脚本后必须重跑**）：

```bash
python3 ~/.agents/skills/ai-fundamental-coverage/scripts/selftest_gate.py   # 必须 exit 0
```

10 个对抗用例：完整作答与合法缺口必须放行；吞节点 / 合并核对项 / 套话 / 数字题糊弄 / 证据无来源 / 一句话缺口 / 造血表缺失 / 表格题无表 必须被打回。退出码非 0 说明闸门已经被改坏，不得交付。

---

## 5. 交付

- `report.md` —— 主交付物：20 个节点逐条、95 项逐行、带来源或缺口
- `coverage_report.md` / `coverage.csv` —— 覆盖率证明（分母、合格率、不合格清单）
- 口头摘要：**合格率 + 最关键的 3 条结论 + 必须补齐的输入清单**

需要 Word/Excel 版本时，加载 `office-docx` / `office-xlsx` 技能从 `report.md` 与 `coverage.csv` 转换，**不要重新组织内容**。

---

## 铁律

1. **分母只有一个**：`bank.json` 里的 20 个节点 / 95 个原子核对项。任何"我已覆盖全部"都必须由第 4 步退出码背书。
2. **不做无声省略**：拿不到就写"未披露 + 取数路径"，这是合格答案，不是失败。
3. **禁止编造**：公告名、编号、链接、机构名、数字一律要能回溯；编造比缺失严重得多。
4. **点对点**：一个核对项一行，第一句直接回答它；分支摘要、模块概述都不能替代核对项。
5. **闸门不过不交付**：宁可交一份带缺口清单的报告，也不交一份看起来完整实则漏答的报告。
6. **占位不替猜**：F19「美股的第1234季度电话会议上确认xxx」原图 xxx 未填，写清缺失输入并给通用框架；不得替用户编一个"确认事项"。

---

## 题库更新（用户改了导图时）

```bash
python3 scripts/mindmap_import.py "<新导图.emmx>" --json /tmp/map.json --md /tmp/map.md
```

对照 `/tmp/map.md` 修改 `scripts/question_bank.json`：新增/删除节点时同步维护 `modules[].items[]` 与 `elements[]`（每个节点拆成可独立核对的原子项），并更新 `source.sha256` 与节点计数。改完重跑第 4 步的自测基线。

---

## 维护须知（改编排脚本前必读）

1. **`agent()` 的 schema 只支持极小的 JSON Schema 子集**：`type/properties/required/additionalProperties/items/enum/const/oneOf`。
   其中 `enum` **必须同时写 `type`**，否则 workflow 会在第一句 `agent()` 处直接抛
   `unsupported JSON schema: ...enum requires type or oneOf`，整个编排一步都不跑。
   正确写法：`status: { type: 'string', enum: ['ok', 'partial', 'missing'] }`。
2. 改动 `coverage_run.js` 后，**先用 `args.modules` 只留 1 个模块做冒烟**（约 2–3 个 agent 调用），
   确认「作答 → 审计 → 补漏 → 复核 → 装配自检」全链路跑通，再放全量 8 个模块。
   冒烟时覆盖率闸门必然报"其余模块缺失"，这是预期现象，不是故障。
3. 三个 python 脚本之间靠**文件名与 markdown 约定**耦合（`parts/<模块>.md`、`blocks/<节点ID>.md`、
   `### [节点ID]` 标题、`**核对项名称**：答案` 行）。动其中任何一个格式约定，必须同时改另外两个
   并重跑 `selftest_gate.py`。
4. 改完 `coverage_run.js` 必须做语法校验（脚本顶层 `return` 由 harness 包在函数里执行，
   直接 `node --check` 会误报 `Illegal return statement`，要按同样方式包一层）：

   ```bash
   { echo "async function __wf(args, agent, pipeline, parallel, phase, log) {"; \
     cat workflows/coverage_run.js; echo "}"; } > /tmp/wrap.mjs && node --check /tmp/wrap.mjs
   ```

   最容易踩的坑：prompt 模板字符串里**不能出现反引号**，否则会截断模板、整个脚本语法报错。
