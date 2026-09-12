# grep 行为笔记与智能化方向

核心问题：**AI agent 什么时候用 grep，想从 grep 得到什么？**
该问题的答案决定智能 grep CLI 的设计方向。

标注：【源码】sst/opencode dev 分支验证（2026-09）；【文档】官方文档；
【观察】我作为 agent 的实际行为 + 对他人 trace 与讨论的观察；【调研】网络来源附出处。

---

## 1. 背景：两家 agent 的 grep 实现

### 1.1 opencode【源码】

入参只有 3 个：`pattern`（正则）、`path`（目录）、`include`（单个文件 glob）。
底层 spawn rg 子进程（系统 rg 优先，否则自动下载 ripgrep 15.1.0），调用字段固定：

```
rg --no-config --json --hidden --no-messages [--glob=<include>] --glob=!**/.git/** -- <pattern> .
```

| 字段 | 作用 |
|---|---|
| `--no-config` | 忽略用户全局 ripgrep 配置，保证行为一致 |
| `--json` | 结构化输出（路径/行号/匹配文本/submatch），opencode 解析后自行格式化 |
| `--hidden` | 搜索隐藏文件 |
| `--no-messages` | 抑制权限/IO 错误噪音 |
| `--glob=<include>` | 仅当传了 include；文件过滤（可写 `*.{ts,tsx}`） |
| `--glob=!**/.git/**` | 始终排除 `.git/` |
| `-- <pattern> .` | 正则 + 搜索根（`.` 相对于解析后的 path 目录） |

**例**：模型发起工具调用 `grep({pattern: "permission", path: "packages/opencode/src", include: "*.ts"})`，
opencode 实际执行的进程是：

```
cwd = <项目根>/packages/opencode/src
rg --no-config --json --hidden --no-messages --glob=*.ts --glob=!**/.git/** -- permission .
```

rg 的 JSON 行被解析、拼路径后，模型看到的输出是：

```
Found 3 matches
/project/skills/packages/opencode/src/tool/grep.ts:
  Line 42:           yield* ctx.ask({
  Line 43:             permission: "grep",
  Line 51:           yield* assertExternalDirectoryEffect(ctx, requested, {
```

没显式传的 flag 都是 rg 默认：**区分大小写**、遵守 `.gitignore`（可用项目根 `.ignore`
放行）、不跨多行。结果硬上限 100 匹配行、单行 2000 字符截断、无翻页。
工具描述中给模型的分工指引：计数/统计走 bash 直跑 `rg`，开放式多轮搜索走 Task 子代理。

### 1.2 Claude Code【文档】

参数面几乎把 rg 常用能力都开放给模型：`pattern/path/glob/type`、
`output_mode = files_with_matches | content | count`、`-A/-B/-C` 上下文行、`-i`、
`-n`、`multiline`、`head_limit`、`offset`。即：三种输出模式、上下文、分页、多行匹配
全由模型按需选择。

另外【调研】：Claude Code 在 2026-04（v2.1.117）把底层从 ripgrep 换成了
**ugrep + bfs**（原生构建）；Aider 用 tree-sitter 驱动的 **grep-ast**；Codex 以
ripgrep 为主、grep 兜底（ceaksan.com《grep, ripgrep, and AI-Powered Text Search》）。

**对比结论**：opencode 极简（3 参数、格式写死），Claude Code 把 rg 参数面交给模型。
两家都未向模型暴露"意图"维度，输出均停留在文本行匹配层。

---

## 2. 核心：AI 什么时候用 grep，想得到什么（6 种意图）【观察】

grep 调用通常只是多步推理的第一步，其结果很少被直接消费，而是用于决定下一步
读哪个文件。以下分类来自我的实际行为（本会话即完整执行过一次"理解 opencode
grep 功能"），并与他人对 agent trace 的观察相互印证（见 §3）。

### 2.1 定位入口（locate）
- **何时**：拿到一个名字（功能名、工具名、报错串），不知道在哪个文件。
- **想要**：极少数几行 file:line，内容不重要，定义处必须排最前。
- **实际行为**：刻意选最有区分度的串作为锚点（如独特短语而非 `grep` 这类泛词），
  命中后立即转 Read 读全文。
- **缺口**：rg 按文件顺序返回，无"定义优先"排名；import/注释/字符串中的命中与
  真实定义混杂。

### 2.2 找调用方 / 上行（usage）
- **何时**：要改一个函数/配置前，评估"谁会受影响"；或理解一个值的来源。
- **想要**：完备的 call site 列表，且知道每一处是调用、定义还是注释。
- **实际行为**：grep 标识符 → 逐个 Read 确认是否为真实调用——等价于手工执行
  LSP findReferences。有 call graph 工具时优先使用。
- **缺口**：文本匹配无法区分符号引用与同名字符串；完备性需人工确认。

### 2.3 理解行为 / 下钻（understand）
- **何时**："这个功能怎么实现的"——探索性问题，起点往往是一个用户可见的词
  （错误信息、flag 名、文档术语）。
- **想要**：入口周围的完整逻辑块（整个函数/类），而非孤立行；随后需要沿 callee
  继续下钻（call graph 下行）。
- **实际行为**：grep 定位 → Read 全文 → 从读到的代码中发现新标识符 → 再 grep/再读，
  多轮循环；每次 grep 后几乎必然紧跟一次同文件 Read，grep 与 Read 成对出现。
- **缺口**：孤立行无上下文，导致一次额外 Read；100 行截断且无排名，宽查询不可用。

### 2.4 找样本学写法（examples）
- **何时**：要写新代码，先看项目里现成的用法惯例（"这里都怎么写 Effect.gen"）。
- **想要**：3~5 个有代表性、互不相同的样本，覆盖主要变体即可。
- **实际行为**：宽搜一把，从前几十条里人工挑选几个有代表性的去读。
- **缺口**：100 条上限常被同一文件或生成代码占满；无去重、无多样性采样。

### 2.5 审计排查（audit）
- **何时**："还有没有地方用旧 API""有没有密钥/eval 残留"——安全与迁移场景。
- **想要**：穷尽结果，并且能确认没有遗漏（知道搜了哪些范围、排除了什么）。
- **实际行为**：宁可多轮窄搜确认，也不信任一次被截断的宽搜。
- **缺口**：100 行截断直接破坏完备性语义；输出缺少"搜索覆盖面"声明。

### 2.6 日志/报错反查（log）
- **何时**：拿着线上日志、error message、堆栈帧找产生它的代码。
- **想要**：产生该串的代码点；日志中的变量部分（数字、ID、引号串）应被泛化容忍。
- **实际行为**：原串搜不到 → 手动截取不变的部分、转义正则元字符、忽略大小写重搜，
  通常要试 2~3 次。
- **缺口**：无字面量模式（日志含大量正则元字符）；无大小写开关；无变量泛化。

**六种意图对输出的诉求互相冲突**：locate 要求最少、audit 要求最全、examples 要求
去重采样、understand 要求完整块——单一固定格式（如 opencode 的 100 行分组文本）
无法同时满足。

---

## 3. 其他人怎么讨论"agent 何时用 grep、想得到什么"【调研】

### 3.1 真实 trace 数据：搜索占 agent 行为的近一半，且高度碎片化

Entire 分析了 1,983 个真实开发 checkpoint、202,142 次工具调用
（entire.io《How We Improved Agentic Search》）：

- **48.8%（98,555 次）的工具调用是搜索相关的**；其中 Read/文件检索 49.0%、
  bash 搜索兜底 23.5%、grep 内容搜索 23.5%。
- **搜索工作流是碎片的**：agent 在 Read、bash 搜索、grep 之间交替——说明
  "raw ripgrep 输出按任意顺序返回"这一默认输出面不够好。
- **速度不是瓶颈**：把搜索换成快得多的 `fff`，端到端只小幅改善；**排名才是**——
  更好排名的 `pgr` 持续提升首查询命中率，使 agent 更早获得相关候选。

### 3.2 "想得到什么"的直接讨论：四种路由

blakecrosley.com《Agent Code Search Has a Token Budget》明确提出：agent 需要知道
自己在做哪一类检索——**exact lookup（精确查找）/ semantic discovery（语义发现）/
related-code exploration（相关代码探索）/ evidence confirmation（证据确认）**，
路由不应隐藏在黑盒中，否则会成为失败源。这与 §2 的六意图分类同构
（locate≈exact lookup、understand/usage≈related-code exploration、audit≈evidence
confirmation、examples 介于 discovery 与 lookup 之间）。

### 3.3 grep 的角色定位：假设生成器

yage.ai《Why Coding Agents Still Use grep as Their Search Backbone》（引 Mike Mason）：
业界收敛到检索漏斗——grep/rg 是第 1 层，负责探索、假设生成、context foraging；
LSP 是假设验证（findReferences、rename、call hierarchy）。grep 的优势不在精确，
而在零预建索引、失败模式为假阳性（而非漏召回）、文本输入输出可组合可调试。
Anthropic 的 context engineering 指南观点一致：just-in-time context，靠工具运行时
动态取数，而非预建 RAG；同时警告：缺少合适的工具与启发式时，agent 会在误用工具
和无效搜索上消耗上下文。

### 3.4 信任问题：模型被训练得只信 grep

HN 关于 Semble（号称比 grep 省 98% token 的代码搜索）的讨论里两条关键观察
（news.ycombinator.com/item?id=48169874）：

- "模型被 RL 得重度依赖 grep，不信任其他形式的结果，会反复重试或重读，
  把省下的 token 全部赔回去"（jerezzprime）。
- "省 token 重要，但同样重要的是 agent 是否信任结果并停止搜索——应该度量整个
  agent loop，而不是单次搜索输出"（Riany）。

对本工具设计的约束：输出形态必须贴近 grep/Read 的习惯（file:line + 代码原文）；
模型不信任新的输出形态时，会通过重试和重读抵消收益。

### 3.5 反面观点：grep-only 检索的 token 开销

- Milvus 博客批评 Claude Code 的 grep-only 检索：一次调试中"对的 10 行被埋在
  500 行噪音里"，一分钟还没找到相关文件（milvus.io）。
- Reddit 反复出现"探索大仓库消耗大量 token"的反馈，社区解法是在 CLAUDE.md 中
  写明查找路径，减少 ls/grep 循环（r/ClaudeAI）。
- ai-grep 的痛点示例：查 "rate limit" 概念，agent 连换 4 个关键词、22 次工具调用、
  $0.56、58 秒才找到——**概念类查询是 grep 的结构性盲区**（github.com/moinulmoin/ai-grep）。

### 3.6 量化对照

- 《Is Grep All You Need?》论文在 Claude Code / Codex CLI / Gemini CLI 等 runtime 上
  测 grep vs 向量检索：inline grep 胜过 inline vector，且 **runtime 对结果的影响
  不亚于检索方法本身**（blakecrosley.com 引述）。
- Morph：agent 60%+ 时间花在搜索上下文；WarpGrep（RL 训练的搜索子代理，每轮 8 路
  并行工具调用）登 SWE-Bench Pro 第一（morphllm.com/agentic-search）。
- Boris Cherny（Claude Code）：agentic search "outperformed everything, by a lot"——
  迭代式 grep 能自我修正，单次向量检索不能。
- Codebase-Memory（arXiv:2603.27277，tree-sitter 知识图谱 MCP）：质量 83% vs 纯
  grep 探索 92%，但 token 省 10 倍；caller ranking 等图查询在 19/31 仓库打平或反超。

### 3.7 输出格式与停止条件的实操共识（ceaksan playbook）

- 返回给 agent 的格式：`file:line` + 至多 2 行上下文、按行去重、gitignore 感知、
  去空行和装饰性注释。
- `head -50` 是最有效的 token 节省手段；`-C N` 会膨胀 2~6 倍，仅必要时用。
- 三个检查点：**0 结果立即换策略**；结果聚集单文件则扩大范围；token 预算过半即停。

---

## 4. 方向结论【观察+调研的收敛】

1. **做意图感知的 grep，而非更快的 grep**。trace 数据证明速度不是瓶颈、
   排名和输出形态才是；六意图（§2）与四类路由（§3.2）相互印证——intent 应作为
   一等参数。
2. **输出形态必须保守**：file:line + 短上下文 + 代码原文，贴近 grep/Read 习惯，
   否则模型不信任、收益被重试抵消（§3.4）。创新放在排名、分块、去重、预算上，
   不改变输出语法。
3. **第一版范围**（rg + tree-sitter，无索引无 embedding）：
   - `--intent locate|understand|usage|examples|audit|log`（log 自动字面量化+变量泛化）；
   - understand 模式把命中扩展到封闭函数/类块，合并"grep 后必跟 Read"的往返（§2.3）；
   - 定义优先排名 + token 预算参数 + 重复命中折叠。
4. **内建停止/升级信号**（§3.7）：0 结果时输出"已尝试什么、建议换什么"；
   结果聚集时提示扩大范围——将检查点作为输出的一部分，而不是依赖 agent 自行判断。
5. **不做的方向**：embedding 语义搜索（ai-grep 等已有实现，且概念查询可交给上层
   agent 迭代）；搜索子代理训练（WarpGrep 方向，超出 CLI 范畴）。全量索引知识图谱
   不重复实现，但可作为可选后端——见 §5。
6. **开放问题**：intent 显式传参 vs 从 pattern 形态推断（倾向显式为主、推断做默认值）；
   与 opencode 既有分工（bash rg / Task 子代理）的衔接；远期可选项 ast-grep
   结构模式与 LSP callHierarchy 后端。

---

## 5. 意图 × codebase-memory-mcp（CBM）：融合方案【源码+观点】

CBM（/project/codebase-memory-mcp，arXiv:2603.27277 官方实现，纯 C + tree-sitter，
162 语言，15 个 MCP 工具 + cli 模式）把仓库索引成持久知识图谱：节点
Function/Method/Class/Route/File…，边 CALLS / IMPORTS / USAGE / TESTS /
USES_TYPE / FILE_CHANGES_WITH 等。其中 `TESTS` 边为"测试排最后"的排名策略
提供了现成信号。

### 5.1 agrep 的实现模式

工作名称 **agrep**（agent grep）。按模式路由：`--intent` 显式指定，缺省为
normal。每个模式包含：实现、服务的意图、预期输出示例、回落行为。
所有模式共用 token 预算参数与 `--json` 双输出；输出统一保持 grep 风格
（file:line + 代码原文），模式间差异仅在于返回哪些结果、如何排序、
附带哪些附加信息。

#### normal（默认模式）

- **实现**：纯 rg（opencode 同款固定 flags）。除 pattern 预处理外不做其他增强：
  识别出日志/报错文本（含大量正则元字符、数字 ID、`%s`/`{}` 占位）时，先自动按
  字面量搜一次；0 结果时再把变量部分泛化为通配重搜一次。
- **服务意图**：log（完全匹配）；同时作为其余所有模式在无索引环境下的回落路径。
- **预期输出**：

```
Found 2 matches
src/ripgrep.ts:
  Line 25: const MAX_RECORD_BYTES = 64 * 1024
  Line 108:   ? Effect.fail(failure(`Ripgrep JSON record exceeded ${MAX_RECORD_BYTES} bytes`))
```

- **0 结果时**：输出已尝试的 pattern 变体和建议（"已按字面量/泛化各搜一次，
  建议缩短为更稳定的子串"），而不是仅返回 "No files found"。

#### locate

- **实现**：图优先——`search_graph(label=Function|Method|Class, name_pattern=…)`，
  图节点即定义。无图回落 rg + tree-sitter：将形如 `export const/func/class X` 的
  定义形态命中排前，import/注释排后。
- **服务意图**：locate。
- **预期输出**（极少行，定义在前）：

```
Found 1 definition, 2 other matches
src/tool/grep.ts:
  Line 20: export const GrepTool = Tool.define(
also in:
  src/tool/registry.ts:
    Line 14: import { GrepTool } from "./grep"
  src/tool/grep.test.ts:
    Line 7: import { GrepTool } from "./grep"
```

#### usage

- **实现**：图 `trace_path(direction=inbound)` 取真 caller，按度排序，
  测试调用折叠到末尾。无图回落 rg 搜标识符 + 启发式剔除定义行/注释，
  输出标注"文本匹配，未经图验证"。
- **服务意图**：usage。
- **预期输出**：

```
Callers of ripgrep.grep (2, graph-verified; 1 test caller folded)
src/tool/grep.ts:
  Line 68:   const result = yield* ripgrep.grep({ cwd, pattern: params.pattern, include: params.include, limit: 100 })
src/search/unified.ts:
  Line 112:  const result = yield* ripgrep.grep({ cwd, pattern, include, limit })
```

#### understand

- **实现**：先按 locate 定位入口 → 取封闭语法块（图：`get_code_snippet`；
  rg：tree-sitter 从命中行向上找函数/类边界）→ 末尾附一跳 callee 名单。
  将 §2.3 中"grep 后必跟 Read"的固定往返合并为一次调用。
- **服务意图**：understand。
- **预期输出**：

```
src/tool/grep.ts — GrepTool (lines 20-95):
  Line 20: export const GrepTool = Tool.define(
  ...（完整函数体，受 token 预算约束，超长则给头部 + 摘要）...
  Line 95: )
calls → ctx.ask, fs.stat, assertExternalDirectoryEffect, ripgrep.grep
```

#### examples

- **实现**：rg 宽搜 → 按文件去重 → tree-sitter 判断命中点 kind（非测试优先）→
  多样性采样 N=3~5（不同文件、不同写法变体）→ 每个样本扩展到封闭块。
  有图时可用 USAGE/TESTS 边加速筛选（可选增强，非必需）。
- **服务意图**：examples。
- **预期输出**：

```
3 samples (from 47 matches in 12 files, deduped)
[1] src/tool/grep.ts — a Tool.define with Effect.gen:
  Line 20: export const GrepTool = Tool.define(
  ...
[2] src/tool/read.ts — minimal tool, no permission ask:
  ...
[3] src/tool/edit.ts — tool with file-lock guard:
  ...
```

#### audit

- **实现**：图——`query_graph` Cypher（如 `MATCH (f:Function) WHERE NOT EXISTS
  { (f)<-[:CALLS]-() } RETURN f`）+ `check_index_coverage` 输出覆盖面声明。
  无图——rg 无截断拉全 + 自行统计搜索面（搜了多少文件、被 ignore 排除了什么）。
  两条路径都必须以覆盖面声明结尾，这是 audit 的语义核心。
- **服务意图**：audit。
- **预期输出**（结果列表从略，关键是尾部声明）：

```
...（完整命中列表，不截断）...
complete: 1,240 files searched, no truncation
coverage: 2 files not indexed — gen/x.ts, vendor/y.c — conclusions do NOT cover them
```

#### impact（仅图，无图明确拒绝）

- **实现**：`detect_changes`，输入为当前 git diff（或两个 ref）。无索引时直接
  报错并提示先执行 `index_repository`；rg 无法实现该意图，不做降级处理。
- **服务意图**：impact（图带来的新意图）。
- **预期输出**：

```
diff touches: ripgrep.grep (src/ripgrep.ts)
blast radius:
  HIGH   GrepTool (src/tool/grep.ts) — direct caller
  MEDIUM unified search (src/search/unified.ts) — direct caller
  LOW    3 test files
```

#### overview（图优先，无图给轻量摘要）

- **实现**：图 `get_architecture`。无图回落：目录树 + 行数/语言统计的轻量摘要，
  标注"未经索引"。
- **服务意图**：overview（onboarding 场景）。
- **预期输出**：

```
codebase-memory-mcp: C (98%), 162 languages via vendored tree-sitter
entry: src/main.c;  hotspots: src/mcp/mcp.c (566K), src/main.c (133K)
packages: pipeline/ mcp/ foundation/ daemon/ ...
clusters: 12 communities; largest: indexing pipeline (214 functions)
```

### 5.2 融合架构：一个 intent 路由层，双后端

```
agrep "<query>" --intent <X>
        │
        ├─ 检测 CBM 索引（存在且 git 状态新鲜）
        │     ├─ locate/usage/understand/audit/impact/overview → 走图（毫秒级）
        │     └─ 无索引 / 图 0 命中 / coverage 不全 → 回落 rg + tree-sitter 封闭块
        └─ log → 始终 rg 层（图无优势）；examples → rg 为主，有图可选筛选测试/度
```

设计要点：

1. **输出统一渲染为 grep 形态**（file:line + 代码原文），即使数据来自图。
   §3.4 的信任约束：模型对 JSON 节点/边形态的信任度低于 grep 风格文本。
   图结果必须通过 `get_code_snippet` 附带源码原文作为佐证。
2. **audit 的完备性分两层提供**：Cypher 返回结果 + `check_index_coverage` 声明
   未覆盖路径，结论自动附带"这些文件未索引，需人工核对"。
3. **冷启动即升级**：无索引仓库先用 rg 返回结果，同时后台执行 `index_repository`
   （普通仓库毫秒~分钟级），后续查询自动切换到图后端——实现 §3.7 的升级检查点。
4. **不重复实现的部分**：调用图、度中心性排名、测试识别、coverage 声明、影响面；
   **agrep 层自身实现的部分**：log 变量泛化、examples 采样渲染、token 预算、
   保守输出形态、无索引环境回落。
5. **调用入口**：CBM 有独立 `cli` 模式（不依赖守护进程/MCP 会话），
   agrep 直接 shell out，不用实现 MCP client。

### 5.3 风险与现状

- CBM 的 opencode 集成中**已有** "plugin adds grep/glob graph lookup"（grep/glob
  调用时注入图结果）——路线 B 是将 intent 路由做进该插件；按"先独立 CLI"的
  计划选择路线 A（CLI 内部调用 CBM cli）。
- 图准确性依赖 tree-sitter 解析质量（论文自评 83% vs 纯探索 92%），图后端必须
  始终带 rg 回落和 coverage 标注，不能将图作为权威来源。
- cli 模式下 watcher 不运行，索引可能陈旧——调用前需要比对 git 状态决定是否先同步。
