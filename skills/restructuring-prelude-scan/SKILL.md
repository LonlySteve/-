---
name: restructuring-prelude-scan
description: 扫描某家上市公司是否出现"重组前戏"信号（聘中介、大额增资尽调、清壳、卖核心资产、现金授信突增、债务洗澡、债券发行与质押、股价异动、控股股东变更、董秘口径变化、频繁停牌、招聘泄露），逐条给三态判定与可回溯证据，并用硬闸门保证 12 条信号一条不漏。当用户问"这家公司是不是要重组/卖壳/易主"、"帮我看看重组前戏"、"有没有重组的迹象"，或要在选股池里筛重组预期标的时使用。
argument-hint: 股票代码（如 300750 / 00700 / NVDA），可附公司名、基准日与观察窗口月数
---

# 重组前戏 · 信号扫描

**题库已固化在本技能里，不需要用户提供思维导图。** 与 `ai-fundamental-coverage`（基本面排查）是**两个独立工作**，
互不调用、互不覆盖：本技能只做导图里「重组前戏」这一棵子树，运行目录也独立（`restructuring_runs/`）。

- 题库（唯一事实来源）：`scripts/question_bank.json`
  —— **4 模块 / 12 个信号节点 / 86 个原子核对项**，另加一张 12 行信号总表 + 6 个汇总核对项
- 回答契约（作答与审计共同判据）：`references/answer_contract.md`
- 题库来源：`AI咨询基本面偏.emmx` 浮动主题「重组前戏」（源节点 ID 219，子树 21 节点）
  - 21 节点 = **12 个信号节点**（逐条作答）+ 8 个说明/子形态节点（转成对应信号的必答核对项，因此不会被吞）+ 1 个 `XX` 占位
  - 说明性子节点举例：`提前还贷/债务重组/大笔减持计提` → 拆进 R06 的三行核对项；`暂无变以公告为准或不回复`、
    `研究战略转型/评估资产整合方案/探讨合作可能性` → 拆进 R10 的两行核对项
- 中心主题「AI咨询基本面偏」及其余浮动主题（公司自身造血能力、催化事件时间线、AIPDF搜索、AI系列）**不在本技能范围**

---

## 0. 先确认三件事（缺就一次问全，不要猜）

1. **股票代码**（必填）
2. **数据基准日**（默认今天）
3. **观察窗口**（默认基准日往前 **24 个月**，可用 `--lookback-months` 调整）

公司名与市场可由代码推断。若用户只说"帮我看看这家公司要不要重组"，先要代码。

---

## 1. 建运行目录（不可跳过）

```bash
RUN="$PWD/restructuring_runs/$(date +%Y%m%d)_<代码>"
python3 ~/.agents/skills/restructuring-prelude-scan/scripts/build_run.py \
    --ticker "<代码>" --name "<公司名>" --market "<A股|港股|美股>" \
    --as-of "<基准日>" --lookback-months 24 --out "$RUN"
```

产物：`bank.json`（冻结题库）、`meta.json`（含观察窗口起止）、`prompts/M*.md`（作答提纲）、
`prompts/RB.md`（总表提纲）、`CHECKLIST.md`、`workflow_args.json`、`parts/`、`blocks/`。

记下脚本打印的分母：**12 个信号节点 / 86 个原子核对项**。后面所有"查完了"的说法都要由它背书。

---

## 2. 跑编排（首选路径）

读 `workflows/coverage_run.js` 的**全文**作为 `workflow` 工具的 `script`，
把 `$RUN/workflow_args.json` 的内容作为 `args` 传入。

脚本内部：
1. **逐模块并行作答**（4 个 agent，各自读 `prompts/M*.md`，写到 `parts/M*.md`）；
2. **独立审计**（换一个 agent，只挑错：逐核对项判 ok/partial/missing，并专门检查**反向证据是否缺失**）；
3. **定点补漏**（只重写不合格信号，写 `blocks/<信号ID>.md`，补丁优先于 parts）并立刻复核；
4. **汇总总表**（读全部已完成的 parts，生成 `parts/RB.md` 信号总表；**不得引入正文没有的新数字**）；
5. **装配自检**，返回紧凑状态。

规模参考：4 个模块 + 总表 ≈ 12–16 个 agent 调用，约 10–20 分钟。

### 降级路径（没有 `workflow` 工具时）

- 用 `subagent`：每个模块一个子 agent（给 `prompts/M*.md` 路径 + 契约路径 + 写入 `parts/M*.md`），
  再各起一个审计 subagent，再对不合格信号起补漏 subagent，最后单独起一个总表 subagent。
- 都没有时：**自己在当前会话里逐模块写 `parts/M*.md`**，写一个模块立刻自检一个模块。
  绝不要"一口气把 86 项都答了"——那正是漏答的根源。

---

## 3. 装配

```bash
python3 ~/.agents/skills/restructuring-prelude-scan/scripts/assemble_report.py --run "$RUN"
```

标题、顺序、核对项清单全由 `bank.json` 决定，模型只提供正文；缺片段会写成显式 `（缺口：未作答）`。

---

## 4. 硬闸门（决定能不能交付）

```bash
python3 ~/.agents/skills/restructuring-prelude-scan/scripts/coverage_check.py --run "$RUN"
echo "gate exit=$?"
```

逐信号、逐核对项独立核对 `report.md`：区块存在、逐行且名称一致、三态判定是否合法、
要求数字/证据/列表的有没有内容、缺口声明是否带取数路径、有没有套话覆盖多项，
以及 **12 行信号总表 + 6 个汇总核对项（含综合判定与免责声明）是否齐全**。

- **退出码 0 才能交付。**
- 退出码 1：拿 `coverage_report.md` 的"不合格清单"，起补漏 agent 写 `blocks/<信号ID>.md`，
  **重跑第 3、4 步**，循环到 0（通常 1–2 轮）。

自测基线（**改动 `scripts/` 下任何脚本后必须重跑**）：

```bash
python3 ~/.agents/skills/restructuring-prelude-scan/scripts/selftest_gate.py   # 必须 exit 0
```

10 个对抗用例：完整作答与合法缺口必须放行；吞掉整条信号 / 合并核对项 / 套话 / 数字题糊弄 /
证据无来源 / 一句话缺口 / 总表缺失 / 结论过短 必须被打回。

---

## 5. 交付

- `report.md` —— 主交付物：12 条信号逐条、86 项逐行、带证据等级与反向证据
- `coverage_report.md` / `coverage.csv` —— 覆盖率证明
- 口头摘要：**综合判定（是否处于重组前戏 + 把握度）+ 最强 3 条信号 + 最弱 3 条信号 + 必须补齐的输入清单**

需要 Word/Excel 版本时，加载 `office-docx` / `office-xlsx` 技能从 `report.md` 与 `coverage.csv` 转换，不要重新组织内容。

---

## 铁律

1. **分母只有一个**：`bank.json` 里的 12 个信号节点 / 86 个原子核对项。任何"我已查全"都必须由第 4 步退出码背书。
2. **反向证据强制**：每条信号都必须写"为什么它可能不是重组信号"。只找支持证据的答案视为不合格——这是本技能区别于普通问答的关键。
3. **区分阶段**：已公告筹划重组的，前戏已结束，必须在『阶段标注』注明，不得继续堆前戏信号。
4. **区分事实与推断**：A/B/C/D 四级；D 级推断不得单独支撑"出现"，且必须显式标注。
5. **不做无声省略**：查不到就写"未披露 + 取数路径"。
6. **禁止编造**：公告名、编号、日期、机构名一律要能回溯。
7. **总表不引入新数字**：RB 只能汇总正文已有的结论与证据。
8. **闸门不过不交付**：宁可交一份带缺口清单的报告，也不交一份看起来完整实则漏答的报告。

---

## 维护须知（改编排脚本前必读）

1. **`agent()` 的 schema 只支持极小的 JSON Schema 子集**：`type/properties/required/additionalProperties/items/enum/const/oneOf`。
   其中 `enum` **必须同时写 `type`**，否则 workflow 会在第一句 `agent()` 处直接抛
   `unsupported JSON schema: ...enum requires type or oneOf`，整个编排一步都不跑。
   正确写法：`status: { type: 'string', enum: ['ok', 'partial', 'missing'] }`。
2. 改动 `coverage_run.js` 后，**先用 `args.modules` 只留 1 个模块做冒烟**（约 2–3 个 agent 调用），
   确认「作答 → 审计 → 补漏 → 复核 → 总表 → 装配自检」全链路跑通，再放全量。
   冒烟时闸门必然报"其余模块缺失"，这是预期现象，不是故障。
3. 四个 python 脚本靠**文件名与 markdown 约定**耦合（`parts/<模块>.md`、`blocks/<信号ID>.md`、
   `### [信号ID]` 标题、`**核对项名称**：答案` 行）。动任何一个格式约定，必须同时改其它几个并重跑 `selftest_gate.py`。
4. 改完 `coverage_run.js` **必须跑 dry-run 校验器**——用桩函数把整个编排真正执行一遍。
   只做 `node --check` 是不够的：模板字符串里混进一个反引号时语法仍然合法，
   但运行时会抛 `ReferenceError: number is not defined`，整个编排一步都不跑
   （这个坑真实发生过）。

   ```bash
   node scripts/check_workflow.js workflows/coverage_run.js        # 必须 exit 0
   ```

   校验器会报告阶段、agent 调用次数与返回值字段；失败时打印具体错误。
5. prompt 模板字符串里**不要出现反引号**；核对项的类型标注（number/list/conclusion）
   用普通括号表述，不要用反引号包裹。
6. 补漏文件**只能按信号 ID 命名**（`R03.md`），不能拿核对项名称当文件名；装配对非 ID 命名的文件一律忽略。
7. 补漏文件若自带提纲表头（`# 模块名`、标的行、`---`），装配只会保留信号标题**之后**的正文；
   但更稳妥的写法是补丁文件首行就写 `### [信号ID] 原文`。

---

## 题库更新（用户改了导图时）

```bash
python3 ~/.agents/skills/ai-fundamental-coverage/scripts/mindmap_import.py "<新导图.emmx>" --md /tmp/map.md
```

对照 `/tmp/map.md` 的「重组前戏」子树修改 `scripts/question_bank.json`：
新增/删除信号时同步维护 `modules[].items[]` 与 `elements[]`，并更新 `source` 子树节点数与
`rubric.dimensions` / `rubric.min_rows`。改完重跑第 4 步的自测基线。
