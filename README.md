# 投研全覆盖 Agent Skills

两个「逐条不漏」的投研排查技能 + 确定性覆盖率闸门。给一只股票代码，就按固定题库跑完整套排查，**并用脚本证明一条都没漏**。

> 本仓库是技能源码，不含任何行情数据、公告原文或分析结果。

---

## 它解决什么问题

把一整套基本面/重组问题清单丢给 agent，让它自己搜、自己答，结果往往是：

- 几条问题被**合并**成一段话糊过去；
- 某几条直接被**跳过**，而且看不出来；
- 用「综合来看表现良好」「后续值得关注」这类**空话**覆盖多个实质问题；
- 问数字的地方给形容词，给数字的地方没有来源。

于是只能一条条复制粘贴去追问。**这个仓库把「不漏答」从一句叮嘱变成了机器可验证的流程。**

---

## 两个技能

| | `ai-fundamental-coverage` | `restructuring-prelude-scan` |
|---|---|---|
| 用途 | 个股基本面逐条排查 | 「重组前戏」信号扫描 |
| 题库规模 | 8 模块 / **20 节点 / 95 个原子核对项** | 4 模块 / **12 信号 / 86 个原子核对项** |
| 汇总表 | 造血能力评分表（9 维度） | 信号总表（12 行 + 6 个汇总项） |
| 典型问题 | 在手订单对 2026–2028 的支撑、研发投入占比与方向、新建扩建项目单位产能投资强度、5% 以上股东减持明细、自身造血九项指标、U 型反转概率 | 是否聘中介、清壳、卖核心资产、现金授信突增、债务洗澡、债券与质押、股价异动、控股股东变更、董秘口径变化、频繁停牌、招聘泄露 |
| 输出形态 | 数值型分析（数字 + 口径 + 来源） | **三态判定**（出现 / 未出现 / 无法判断）+ 证据等级 |
| 运行目录 | `fundamental_runs/<日期>_<代码>/` | `restructuring_runs/<日期>_<代码>/` |

两者**完全独立**：各自题库、各自引擎、各自运行目录，互不调用。

---

## 核心机制：四层防漏

| 层 | 做法 | 堵住什么 |
|---|---|---|
| 1. 题库固化 | 思维导图解析成 `question_bank.json`，作为**唯一事实来源** | 分母不由模型临场判断 |
| 2. 原子化核对项 | 一个节点拆成 N 个**必须各自独占一行**的核对项 | 合并作答、用一段话覆盖多项 |
| 3. 独立审计 | 换一个 agent，只挑错、不写内容，逐项判 `ok/partial/missing` | 作者自查会自我美化 |
| 4. 确定性闸门 | 纯脚本解 `report.md` + 题库，**不信装配层的自述** | 漏项、套话、无来源、一句话缺口 |

### 举例：什么叫「原子化」

基本面技能的 F14「自身造血」不是一个问题，而是 **11 行必须各自带数字**的核对项：单季经营现金流、销售收现/营收、短期应收占比、坏账计提比例、核心业务毛利率、净利润与现金流匹配度、存货周转天数、合同负债、产能利用率、指标表格、结论。**少一行，闸门直接打回。**

重组技能同理：原图里「董秘口径变化」下面那两种具体形态（`暂无变化以公告为准` / `研究战略转型·评估资产整合`）各自单独成行，不可能被吞。

### 关于「缺口」

**`未披露` + 取数路径（去哪查、查什么）是合格答案**，一句话的「未披露」不是。这样既不会逼模型编数据，也不允许它用模糊话敷衍。

重组技能另加两条硬约束：

- **反向证据强制**：每条信号都必须回答「它为什么可能**不是**重组信号」（聘中介也可能是年报审计轮换、卖资产也可能是正常处置）。
- **证据分级 A/B/C/D**：公告级事实 A、公开数据 B、媒体 C、纯推断 D —— **D 级不得单独支撑「出现」**。

---

## 仓库结构

```
skills/
├── ai-fundamental-coverage/
│   ├── SKILL.md                    # 技能入口：触发条件、四步流程、铁律、维护须知
│   ├── references/
│   │   └── answer_contract.md      # 回答契约：证据分级、各主题口径公式、反失败模式
│   ├── scripts/
│   │   ├── question_bank.json      # ★ 唯一事实来源（20 节点 / 95 核对项）
│   │   ├── build_run.py            # 建运行目录 + 生成逐模块作答提纲
│   │   ├── assemble_report.py      # 按题库顺序装配（缺片段写显式占位）
│   │   ├── coverage_check.py       # ★ 硬闸门（exit 0/1）
│   │   ├── selftest_gate.py        # 闸门自测基线（10 个对抗用例）
│   │   └── mindmap_import.py       # .emmx 思维导图解析（重新烘焙题库用）
│   └── workflows/
│       └── coverage_run.js         # 编排：作答 → 审计 → 补漏 → 复核 → 总表 → 自检
└── restructuring-prelude-scan/
    └── （同构，题库为 12 信号 / 86 核对项）
```

---

## 安装

```bash
git clone https://github.com/LonlySteve/-.git
cp -R -/skills/* ~/.agents/skills/
```

安装后，支持技能目录的 agent 运行时会自动发现它们（技能名前缀为 `ai-fundamental-coverage`、`restructuring-prelude-scan`）。

---

## 使用

### 方式 A：交给 agent（推荐）

直接说：

```
分析 600519 贵州茅台 的基本面（基准日 2026-10-06）
帮我看看 300750 宁德时代 是不是要重组（观察窗口 24 个月）
```

技能会自动完成：建运行目录 → 冻结题库 → 分支并行作答 → 独立审计 → 定点补漏 → 装配 → 闸门校验。

### 方式 B：手动四步

```bash
SKILL=~/.agents/skills/ai-fundamental-coverage
RUN="$PWD/fundamental_runs/$(date +%Y%m%d)_600519"

# 1) 建运行目录（会打印分母：20 节点 / 95 核对项）
python3 $SKILL/scripts/build_run.py --ticker 600519 --name 贵州茅台 \
    --market A股 --as-of 2026-10-06 --out "$RUN"

# 2) 跑编排：把 $SKILL/workflows/coverage_run.js 的全文作为 workflow 工具的 script，
#    把 "$RUN/workflow_args.json" 的内容作为 args 传入
#    （没有 workflow 工具时用 subagent 逐模块跑，或自己在会话里逐模块写）

# 3) 装配
python3 $SKILL/scripts/assemble_report.py --run "$RUN"

# 4) 闸门：退出码 0 才能交付
python3 $SKILL/scripts/coverage_check.py --run "$RUN"; echo "gate exit=$?"
```

退出码 1 时，拿 `coverage_report.md` 的「不合格清单」写 `blocks/<节点ID>.md` 补丁，
重跑第 3、4 步，循环到 0。

---

## 产出物

| 文件 | 内容 |
|---|---|
| `report.md` | 主交付物：逐节点、逐核对项、带来源或明确缺口 |
| `coverage_report.md` | 覆盖率核查报告：分母、合格率、不合格清单与补漏方式 |
| `coverage.csv` | 逐节点明细（含「占位符」列，可核验没有虚高） |
| `CHECKLIST.md` | 给人看的核对清单 |
| `assembly.json` | 装配诊断（每节点哪些核对项被填） |

---

## 验证

```bash
python3 skills/ai-fundamental-coverage/scripts/selftest_gate.py        # 必须 exit 0
python3 skills/restructuring-prelude-scan/scripts/selftest_gate.py     # 必须 exit 0
```

每个自测跑 10 个对抗用例，**要求闸门既不漏放行、也不误杀**：

| 用例 | 期望 |
|---|---|
| 完整作答 / 合法缺口（未披露 + 取数路径） | exit 0 放行 |
| 吞掉整条节点 / 合并两个核对项 / 空话套话 | exit 1 拒绝 |
| 数字题只给定性 / 证据题无来源 / 缺口一句话 | exit 1 拒绝 |
| 汇总表缺失 / 表格题不造表（结论过短） | exit 1 拒绝 |

另外带一条**指标不变量断言**：凡是「整条节点缺失」的节点，其合格数必须为 0。
这条断言专防一类隐蔽 bug —— 装配占位符 `（缺口：未作答）` 长 8 字，一度能骗过列表类的长度校验、
使合格数虚高（**退出码不变，只有指标失真**）。把修复撤掉，自测会立刻报
`R2x 占位符被算作合格（合格 1 + 占位 7 > 总数 7）`。

---

## 维护与扩展

**改了思维导图？** 重新解析并对照更新题库：

```bash
python3 skills/ai-fundamental-coverage/scripts/mindmap_import.py "<导图.emmx>" --md /tmp/map.md
```

新增/删除节点时，同步维护 `question_bank.json` 里的 `modules[].items[]` 与 `elements[]`，
并更新 `source` 的节点计数与 `rubric`（总表维度、`min_rows`）。改完**必须重跑自测基线**。

**改编排脚本？** 先看 `SKILL.md` 的「维护须知」，里面记着两个已知坑：

1. `agent()` 的 schema 只支持很小的 JSON Schema 子集，`enum` **必须同时写 `type`**，否则整个编排一步都不跑；
2. prompt 模板字符串里**不能出现反引号**，否则会截断模板导致语法错误。改完用 harness 的包装方式做 `node --check`：
   ```bash
   { echo "async function __wf(args, agent, pipeline, parallel, phase, log) {"; \
     cat workflows/coverage_run.js; echo "}"; } > /tmp/wrap.mjs && node --check /tmp/wrap.mjs
   ```

---

## 环境要求

- Python 3.10+（三个脚本只用标准库，无第三方依赖）
- 运行 agent 需具备：文件读写、联网检索、以及并行子任务能力（`workflow` 或 `subagent`）
- 无 `workflow` 工具时可按 `SKILL.md` 的降级路径，用 `subagent` 逐模块跑

---

## 说明

- 两个技能的题库来源是一张本地思维导图（`.emmx`）；`question_bank.json` 里保留了其 sha256 作为溯源，文件路径已做脱敏。
- 报告质量取决于公开数据的可得性。**取不到就写「未披露 + 取数路径」，不会用推测填空。**
- 所有结论来自公开信息，**不构成投资建议**。
