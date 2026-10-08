// AI咨询基本面偏 · 全覆盖编排
// 用法：把 build_run.py 生成的 workflow_args.json 内容作为 args 传入本脚本。
// 结构：作答(每模块1个) → 独立审计(换agent只挑错) → 定点补漏 → 复核 → 汇总自检
// 返回紧凑状态；正文全部落在磁盘 <run_dir>/parts 与 /blocks。

const runDir = args.run_dir;
const bankPath = args.bank_path;
const contractPath = args.contract_path;
const meta = args.meta;
const modules = args.modules;

const HEAD = `你在执行一次"逐节点全覆盖"的股票基本面排查，不允许漏答、不允许合并作答。
标的：${meta.name}（${meta.ticker}）　市场：${meta.market}　数据基准日：${meta.as_of}
运行目录：${runDir}
题库（唯一事实来源，只读）：${bankPath}
回答契约（必读）：${contractPath}`;

const ANSWER_RULES = `
硬性要求：
1. 先读题库与契约，再读你的作答提纲（提纲里已列出每个节点必须逐行回答的"原子核对项"）。
2. 每个原子核对项**单独占一行**，格式：**<核对项名称>**：<答案>。名称必须与提纲完全一致，
   一行一个，禁止合并、禁止省略、禁止改名。漏掉任何一行，整条会被硬闸门打回。
3. 数字必须带来源（公告名/编号+日期，或投关/业绩说明会原文，或数据机构+链接）。
4. 查不到就写"未披露"/"未能获取"，并给出**取数路径**（去哪个文件、哪个栏目查什么）。
   缺口声明是合格答案，且必须写足；一句话的"未披露"会被打回。
5. 禁止空话套话（"综合来看表现良好""值得关注"）；禁止编造公告名、编号、机构名、数字。
6. 需要展开的分析写在各核对项之后，用 #### 分析 起头，不得替代核对项。
7. 用 write 工具把成品写到指定 part 文件；写完后用 read 自查一次，确认每个核对项都在。
8. 提纲里核对项后面的类型标注（number / list / conclusion 等）只供你参考，
   不要抄进答案正文。`;

phase('作答');

const audited = await pipeline(
  modules,

  // 阶段 1：逐模块作答
  async (m) => {
    const text = await agent(
      `${HEAD}

## 你的任务（作答 · ${m.id} ${m.title}）
1. read 作答提纲：${m.prompt_path}
2. 按提纲要求联网检索并逐项作答（本模块 ${m.item_ids.length} 个节点 / ${m.element_count} 个原子核对项）。
3. 把成品写入：${m.part_path}
${ANSWER_RULES}`,
      { label: `作答 ${m.id} ${m.title}`, phase: '作答' }
    );
    return { module: m, answerText: text };
  },

  // 阶段 2：换一个 agent 独立审计，不合格就定点补漏并复核
  async (prev, m) => {
    if (!prev) return { module: m.id, title: m.title, status: 'error', note: '作答阶段失败' };

    const audit = await agent(
      `${HEAD}

## 你的任务（独立覆盖审计 · ${m.id} ${m.title}）
你是审计员，不是作者。你的唯一目标是**找出漏答与敷衍**，不要替作者美化。
1. read 题库：${bankPath} —— 找到模块 ${m.id} 下的节点与每个节点的原子核对项清单。
2. read 作答文件：${m.part_path}
3. read 契约：${contractPath}
4. 逐个节点、逐个原子核对项核对：
   - 该核对项是否单独占一行、名称是否与题库完全一致？
   - 问数字的有没有数字？要求表格的有没有真表格？要求来源的有没有可回溯来源？
   - 是否把若干核对项合并成一句？是否用"综合来看"这类套话覆盖多项？
   - 缺口声明是否写清了取数路径（一句话"未披露"算不合格）？
5. 只统计本模块（${m.item_ids.join('、')}）的节点。status 取 ok / partial / missing。`,
      {
        label: `审计 ${m.id} ${m.title}`,
        phase: '审计',
        schema: {
          type: 'object',
          properties: {
            module_id: { type: 'string' },
            items: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  id: { type: 'string' },
                  status: { type: 'string', enum: ['ok', 'partial', 'missing'] },
                  missing_elements: { type: 'array', items: { type: 'string' } },
                  reason: { type: 'string' },
                  fix: { type: 'string' }
                },
                required: ['id', 'status', 'reason', 'fix'],
                additionalProperties: false
              }
            }
          },
          required: ['module_id', 'items'],
          additionalProperties: false
        }
      }
    );

    if (!audit) return { module: m.id, title: m.title, status: 'audit_failed', note: '审计 agent 未返回结构化结果' };

    const bad = (audit.items || []).filter((it) => it.status !== 'ok');
    if (bad.length === 0) {
      return { module: m.id, title: m.title, status: 'ok', failed_items: [] };
    }

    // 定点补漏：只重写不合格节点，写 blocks/<节点ID>.md（补丁优先于 parts）
    const listed = bad
      .map((it) => `- [${it.id}] status=${it.status}\n  原因：${it.reason}\n  要求：${it.fix}\n  待补核对项：${(it.missing_elements || []).join('、') || '(见题库)'}`)
      .join('\n');

    await agent(
      `${HEAD}

## 你的任务（定点补漏 · ${m.id} ${m.title}）
审计员判定下面这些节点不合格。请**只重写这些节点**，其余不要动。
${listed}

要求：
1. read 题库 ${bankPath}，找到这些节点的**全部**原子核对项（不是只补缺的那几项，整条重写完整）。
2. read 原作答 ${m.part_path} 作为底稿，read 契约 ${contractPath}。
3. 每个节点写**一个**补丁文件：${runDir}/blocks/<节点ID>.md
   - <节点ID> 就是节点编号本身（如 F19、F20），**不是**核对项名称；
     一个节点一个文件，禁止用"needs_input.md""q_framework.md"这类名字建文件。
   - 文件内容**只写该节点区块本身**，不要复制提纲表头、标的行、"---"分隔线，也不要重复标题。
     第一行就是「### [<节点ID>] <该节点原图原文>」，紧跟着逐行核对项：
   ### [<节点ID>] <该节点原图原文>
   **<核对项名称>**：<答案>
   ...（该节点全部核对项，一行一个，一个不少）
   #### 分析
   <展开分析>
4. 先把不合格的原因真正解决（补数字、补来源、补取数路径、拆开合并项），不要只做格式搬运。
5. 不要修改 ${m.part_path}，也不要修改 ~/.agents/skills 下的任何脚本或题库文件。
${ANSWER_RULES}`,
      { label: `补漏 ${m.id} ${m.title}`, phase: '补漏' }
    );

    // 立刻复核
    const recheck = await agent(
      `${HEAD}

## 你的任务（补漏复核 · ${m.id} ${m.title}）
1. read 题库 ${bankPath}，确认模块 ${m.id} 下被判定不合格节点（${bad.map((b) => b.id).join('、')}）的全部原子核对项。
2. read 补丁文件：${runDir}/blocks/ 下对应 <节点ID>.md
3. 重新判定每个节点 status（ok / partial / missing）。仍不合格的，把仍缺的核对项逐条列进 missing_elements。`,
      {
        label: `复核 ${m.id} ${m.title}`,
        phase: '复核',
        schema: {
          type: 'object',
          properties: {
            module_id: { type: 'string' },
            items: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  id: { type: 'string' },
                  status: { type: 'string', enum: ['ok', 'partial', 'missing'] },
                  missing_elements: { type: 'array', items: { type: 'string' } },
                  reason: { type: 'string' }
                },
                required: ['id', 'status', 'missing_elements', 'reason'],
                additionalProperties: false
              }
            }
          },
          required: ['module_id', 'items'],
          additionalProperties: false
        }
      }
    );

    const still = ((recheck && recheck.items) || []).filter((it) => it.status !== 'ok');
    return {
      module: m.id,
      title: m.title,
      status: still.length ? 'partial' : 'patched',
      failed_items: still.map((s) => s.id),
      residual: still.map((s) => `${s.id}: ${s.reason}`)
    };
  }
);

// 阶段 3：装配 + 自检（仅供参考；最终闸门由 Lead 独立重跑）
// 阶段 3：汇总总表（只能汇总已有正文，不得引入新数字）
const rbSpec = args.rubric;
if (rbSpec) {
  phase('总表');
  await agent(
    `${HEAD}

## 你的任务（汇总总表 · ${rbSpec.id} ${rbSpec.title}）
1. read 提纲：${rbSpec.prompt_path}
2. read 各模块已完成的作答文件（提纲里列了路径），**只能基于它们已写下的结论与证据**汇总，
   不得引入正文中未出现的新数字、新来源。
3. 按提纲要求生成总表并写入：${rbSpec.part_path}
   首行必须是标题行「### [${rbSpec.id}] ${rbSpec.title}」。`,
    { label: `总表 ${rbSpec.id}`, phase: '总表' }
  );
}

phase('装配自检');

const gate = await agent(
  `你在 ${runDir} 下做装配与覆盖率自检。
依次执行（用 bash）：
1. python3 ~/.agents/skills/ai-fundamental-coverage/scripts/assemble_report.py --run ${runDir}
2. python3 ~/.agents/skills/ai-fundamental-coverage/scripts/coverage_check.py --run ${runDir}
然后 read ${runDir}/coverage_report.md 的"不合格清单"部分（若为空则说明通过）。
只返回：闸门退出码、合格节点数/总数、合格核对项数/总数、以及不合格节点的 ID 与一句话原因。不要复述报告正文。`,
  { label: '装配与自检', phase: '装配自检' }
);

const summary = (audited || []).filter(Boolean).map((r) => ({
  module: r.module,
  title: r.title,
  status: r.status,
  failed_items: r.failed_items || []
}));

log(`编排结束：${summary.filter((s) => s.status === 'ok').length}/${summary.length} 个模块一次通过`);

return {
  run_dir: runDir,
  ticker: meta.ticker,
  name: meta.name,
  modules: summary,
  gate_report: gate
};
