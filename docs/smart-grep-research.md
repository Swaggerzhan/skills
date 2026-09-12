# 智能 grep 调研与设计结论

调研问题：能否在 grep 之上引入小模型/意图路由，为主工作模型返回更高质量的上下文？
本文是调研结论与最终收敛的设计决策记录，自包含。调研时间 2026-09。

## 一句话结论

grep 不可被语义检索替代（完备枚举 vs top-k 抽样是两种契约），但可以被
"全兼容 grep + 枚举化 intent 路由 + 确定性检测器 + 可选小模型 rerank/扩展"
的融合工具增强。小模型只按在洪水截断和语义扩展两个位置，不做路由、不碰精确路径。

## 已有生态（均已核实）

| 项目 | 形态 | 关键点 |
|---|---|---|
| [tobi/qmd](https://github.com/tobi/qmd)（29.6k★） | 本地小模型检索管线 | 三个 GGUF 模型各司其职：1.7B 查询扩展、embeddinggemma-300M 嵌入、qwen3-reranker-0.6B 重排；typed sub-query（lex/vec/hyde）即枚举路由；MCP `query` 有 `intent` 参数。主战场是 markdown 知识库，代码靠 tree-sitter AST 分块（TS/JS/Py/Go/Rust），无调用图 |
| [mixedbread-ai/mgrep](https://github.com/mixedbread-ai/mgrep)（4.4k★） | 云端 RAG 的 grep 外壳 | 文件上传云端 Store，检索+rerank 在云端；`--agentic` 子代理拆查询，`-a` 生成答案。官方定位"complement grep, not replace"。私有代码场景因上云被硬性排除 |
| [yoanbernabeu/grepai](https://github.com/yoanbernabeu/grepai) | 纯本地语义代码搜索 | Ollama 嵌入 + 调用图 + MCP server |
| [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)（42.8k★） | 知识图谱 + grep 融合 | `search_code` 即"graph-augmented grep"：命中归属符号、定义优先排序，raw grep 行始终保留；PreToolUse hook 观察 Grep/Glob/Bash 注入图谱符号（fail-open，绝不拦截）；`check_index_coverage` 让"0 结果"可区分"没索引"与"真没有"；本地二进制，无 LLM 内置 |
| Claude Code Explore 子代理 | 小模型在 agent 层 | 便宜模型在独立上下文里跑 grep/读文件，只回蒸馏结论（v2.1.198 前固定 Haiku，之后继承主模型、上限 Opus） |
| SWE-grep / WarpGrep / Omnigrep | RL 训练的小模型搜索代理 | Cognition/Morph/Polarity 各自宣称 SOTA，但**评测均未公开**，无法复用 |

## 关键实证数据

- **ContextBench / Turbopuffer**（[视频](https://www.youtube.com/watch?v=zKk7sDMGDEQ)，50 任务）：原生 Claude Code
  每 3 次 Read 浪费 1 次（文件精度 65%）；加 windowed grep（读限 50 行）降到 1/5；再加语义搜索降到 1/8、
  精度 87%。**第一跳改进零 LLM、零索引**——仅"grep 返回匹配行±窗口"就吃掉大半浪费。
  语义搜索赢在"文件间无共同关键词"的任务，grep 赢在 import 追踪。
  关键引述：Cursor 生产环境语义检索 +24% 相对答案准确率，原因是"Cursor 的模型知道何时、为何调用
  语义搜索；Claude Code 只是把它摆在工具列表里"——**显式路由是收益分水岭**。
- **arXiv 2607.06184**（2,500 条真实轨迹）：OpenCode 的 re-read-churn（同一文件反复读）43.6%，
  Claude Code 16.9%；另有 Shell-over-Tool 检测器——模型会用 Bash 跑 rg 绕过结构化 Grep 工具，
  只做工具层增强会漏掉这部分流量。
- **cbm 论文 arXiv 2603.27277**：5 次结构查询 ~3,400 token vs 逐文件探索 ~412,000 token。
- **Morph [agentic search 综述](https://www.morphllm.com/agentic-search)**：高效搜索行为 =
  并行 4~12 个查询 + 早停 + 多跳追踪；Cognition 实测并行 4→8 使轮次 6→4 质量不变（二手转引）。
  **轮次本身是成本**，不只是 token。

## 设计决策（收敛后）

### D1: grep 必须保留，语义只能并存

grep 的契约是完备枚举：0 结果是"范围内不存在"的证明。语义检索是 top-k 抽样：0 结果无法区分
"没索引/索引过期/不够相似/真没有"。删掉 grep 后，完备性判断只剩整文件 Read，token 反而更多。
重构追调用点、审计、下否定结论都依赖完备性。

### D2: intent 参数做显式路由，枚举化，留空=raw

- 签名形如 `grep(pattern, path, intent, note?)`，intent 枚举：
  `exact_literal | symbol_trace | usage_find | concept_search`，note 为 ≤10 词补充。
- 路由交给主模型（系统里最聪明的组件，边际成本为零）；小模型不做路由。
- **留空必须等于原始 grep**：不知道 intent 存在的模型/脚本行为逐字节不变。
  "留空则工具自动转译"会在默认路径引入不确定性，破坏向后兼容，且回到"从 pattern 猜意图"的老路。
  想要自动升级体验，做成按 agent 的 opt-in 配置。

### D3: 透明增强的红线——标注可透明，干预需 intent

不暴露 intent 时也能做增强（cbm hook 与 Claude Code 的 notice 机制已验证模型能消费标注），
但分界线是：

- **标注（annotate）**：附元数据/警告/选项，不动结果。安全，可透明。例：
  `[2,147 matches in 312 files; showing first 50] [by-file top: ...] [options: narrow | scope | re-run with intent=concept_search]`。
- **干预（intervene）**：截断/重排/替换结果。结果是否有问题可客观判定，但该怎么处理依赖意图
  （审计要完备集、探索要过滤集），无 intent 时干预 = 模型不知情地破坏契约，比显式路由更危险。

### D4: 检测器全用确定性规则，小模型只出现在两个位置

| 分工 | 谁做 | 原因 |
|---|---|---|
| 声明意图、选管线 | 主模型（枚举参数） | 一次性决策，它最强，成本为零 |
| flood/零命中/语法错/vendor 集中检测、词形扩展（camelCase 拆分）、完备性保障 | 确定性代码 | 必须可靠、零延迟、无幻觉 |
| 查询扩展（零命中时生成同义说法） | 小生成模型（QMD 微调 1.7B 先例） | 需要词汇多样性，规则做不到 "auth ≈ session" 的语义跳跃 |
| 洪水时逐条相关性打分 | 小 reranker（QMD qwen3-reranker-0.6B 先例） | per-item 重复判断，主模型做烧几千 token，0.6B 本地亚秒 |

为每次 grep 都挂 AI 判断意味着 90% 正常调用也吃延迟和误判风险；误标等于往主模型上下文
注入错误引导。v1 可以零小模型：windowed 返回 + 批量 pattern + 结构化零命中/洪水提示，
已能吃到实证收益的大头。

### D5: 融合后端优先选知识图谱而非 chunk-RAG

图谱给的是确定性结构事实（"该命中在函数 X 内，X 有 7 个调用方"），与 grep 本体共享同一
可信级别；RAG 给的是概率性排序，混入会稀释契约。图谱还有 coverage 元数据可判定缺口。
硬约束：索引缺失/过期/解析失败时整体降级纯 grep 并显式声明"增强不可用"。

### D6: intent → 管线映射

| intent | 行为 |
|---|---|
| `exact_literal` / 留空 | 纯 grep，一字不改 |
| `symbol_trace` | grep 行 + 归属符号/定义标记；图谱补充动态调用等 grep 看不见的引用，标注"完备性以 grep 为准" |
| `usage_find` | grep 文本命中 ∪ 图谱入边，去重 |
| `concept_search` | 语义查询 + grep 并行，RRF/小 reranker 融合；结果注明是过滤子集 |
| 零命中（任何 intent） | ① coverage 检查 → ② 确定性词形扩展重跑 → ③ 小模型语义扩展；每步标注来源 |

### D7: 工程注意点

- Bash 通道会绕过结构化工具（轨迹研究实证）：要么 hook 同时覆盖 Bash，要么接受该流量不增强。
- 支持一次调用传多个 pattern（批量并行）——省的是轮次。
- 工具描述质量直接决定 intent 功能有没有用：每个枚举值的适用条件要写死，防止模型
  把 concept_search 滥用在本需完备答案的场景。

## 参考来源

- 论文：[arXiv 2607.06184 轨迹结构诊断](https://arxiv.org/html/2607.06184v1) ・
  [arXiv 2603.27277 cbm](https://arxiv.org/abs/2603.27277)
- 数据：[ContextBench 评测视频](https://www.youtube.com/watch?v=zKk7sDMGDEQ)（配套
  [细节视频](https://www.youtube.com/watch?v=6t29UHJQpvA)、[转录](https://finance.biggo.com/news/aed3a6d02a3f1d95)）
- 文章：[Morph agentic search](https://www.morphllm.com/agentic-search) ・
  [Claude Code 流量实测](https://medium.com/@georgesung/tracing-claude-codes-llm-traffic-agentic-loop-sub-agents-tool-use-prompts-7796941806f5) ・
  [Mixedbread Search 原理](https://www.mixedbread.com/blog/mixedbread-search) ・
  [Langfuse agent 轨迹方法](https://langfuse.com/resources/engineering/coding-agent-tracing)
- 文档：[Claude Code 子代理](https://docs.claude.com/en/docs/claude-code/sub-agents) ・
  [工具行为](https://docs.claude.com/en/docs/claude-code/tools-reference)

置信度标注：ContextBench 数字取自视频描述与转录（一手为演讲）；Morph 文中 Cognition/Relace/
WarpGrep 数字为二手转引；其余均为一手来源（README/官方文档/论文）。
