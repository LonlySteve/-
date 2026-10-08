#!/usr/bin/env node
/**
 * 编排脚本 dry-run 校验器
 *
 * 为什么需要它：`node --check` 只能查语法。模板字符串里混进一个反引号时，
 * 语法仍然合法（会被解析成数组字面量 + 新模板），但**运行时**抛
 * `ReferenceError: number is not defined`，整个编排一步都跑不起来。
 * 本脚本用桩函数把 coverage_run.js 真正执行一遍，专门抓这类问题。
 *
 * 用法：
 *   node check_workflow.js <coverage_run.js> [args.json]
 *
 * 退出码 0 = 可执行；1 = 有错。
 */
import fs from 'node:fs';

const scriptPath = process.argv[2];
const argsPath = process.argv[3];
if (!scriptPath) {
  console.error('用法: node check_workflow.js <coverage_run.js> [args.json]');
  process.exit(2);
}

const body = fs.readFileSync(scriptPath, 'utf8');

// 默认假 args：两个模块 + 一张总表，够走遍全部分支
const FAKE_ARGS = {
  run_dir: '/tmp/dryrun',
  bank_path: '/tmp/dryrun/bank.json',
  contract_path: '/tmp/dryrun/contract.md',
  meta: { ticker: '000000', name: 'dryrun', market: 'A股', as_of: '2026-01-01' },
  modules: [
    { id: 'M1', title: 'A', prompt_path: '/tmp/dryrun/p1.md', part_path: '/tmp/dryrun/p1.out', item_ids: ['X01', 'X02'], element_count: 4 },
    { id: 'M2', title: 'B', prompt_path: '/tmp/dryrun/p2.md', part_path: '/tmp/dryrun/p2.out', item_ids: ['X03'], element_count: 2 }
  ],
  rubric: { id: 'RB', title: '总表', prompt_path: '/tmp/dryrun/rb.md', part_path: '/tmp/dryrun/rb.out' }
};
const args = argsPath ? JSON.parse(fs.readFileSync(argsPath, 'utf8')) : FAKE_ARGS;

const calls = [];
const phases = [];

/** 按 schema 造一个形状正确的返回值，好让后续分支（补漏/复核）也被执行到 */
function fakeForSchema(schema) {
  const obj = {};
  for (const [key, spec] of Object.entries(schema.properties || {})) {
    if (spec.type === 'array') {
      obj[key] = [{ id: 'X01', status: 'partial', missing_elements: ['e1'], reason: 'dryrun', fix: 'dryrun' }];
    } else if (spec.enum) {
      obj[key] = spec.enum[0];
    } else {
      obj[key] = 'dryrun';
    }
  }
  return obj;
}

async function agent(prompt, opts = {}) {
  if (typeof prompt !== 'string' || !prompt.trim()) throw new Error('agent() 收到空 prompt');
  calls.push(opts.label || 'agent');
  return opts.schema ? fakeForSchema(opts.schema) : 'dryrun-ok';
}

async function pipeline(items, ...stages) {
  const out = [];
  for (let i = 0; i < items.length; i++) {
    let prev = items[i];
    try {
      for (const stage of stages) prev = await stage(prev, items[i], i);
      out.push(prev);
    } catch (err) {
      out.push(null);
      console.error(`  [pipeline 第 ${i} 项抛错] ${err.message}`);
    }
  }
  return out;
}

async function parallel(thunks) {
  const res = await Promise.all(thunks.map(async (t) => {
    try { return await t(); } catch { return null; }
  }));
  return res;
}

function phase(title) { phases.push(title); }
function log(msg) { console.log('  log:', msg); }

const fn = new Function(
  'args', 'agent', 'pipeline', 'parallel', 'phase', 'log',
  `return (async () => {${body}\n})();`
);

try {
  const result = await fn(args, agent, pipeline, parallel, phase, log);
  console.log(`✅ dry-run 通过：${scriptPath}`);
  console.log(`   阶段: ${phases.join(' → ') || '(未声明)'}`);
  console.log(`   agent 调用: ${calls.length} 次`);
  if (result && typeof result === 'object') {
    const keys = Object.keys(result);
    console.log(`   返回字段: ${keys.join(', ')}`);
    if (!('run_dir' in result)) console.log('   ⚠️ 返回值缺少 run_dir');
  } else {
    console.log('   ⚠️ 返回值不是对象');
    process.exitCode = 1;
  }
} catch (err) {
  console.error(`❌ dry-run 失败：${scriptPath}`);
  console.error(`   ${err.name}: ${err.message}`);
  if (err.stack) console.error(err.stack.split('\n').slice(1, 4).join('\n'));
  process.exit(1);
}
