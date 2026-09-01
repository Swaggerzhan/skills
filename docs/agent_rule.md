# 系统 Prompt

本文档描述两个 agent 的系统 Prompt 规则：pi（本仓库）与 opencode。内容基于双方当前源码与配置，
非承诺性接口。

## 索引

- 前置定义：每轮请求与 prefill（含工具定义与 SP 同属头部前缀）
- 一、pi
  - 结构：一个字符串，两个互斥分支
  - 固定尾部 / 优先级 / 默认模板
  - Guidelines 的组装顺序
  - 默认 4 工具时的实际 Prompt
  - 自定义 SYSTEM.md 覆盖后的样子
  - 工具切换会重建 Prompt
- 二、opencode
  - 架构差异
  - system 消息的拼接
  - 子代理上下文与 AGENTS.md / CLAUDE.md 加载
  - 工具过滤：permission 硬执行，不靠 Prompt 文字
  - 极简 Code agent 示例 / 该 Code agent 最终看到的东西
  - example for opencode coder agent（4 工具能力表）
  - opencode 可封禁功能全景与推荐封禁
- 官方协议参考（缓存前缀失效的依据）

## 前置定义：每轮请求与 prefill

符号：SP = System Prompt（系统提示词）；U = 用户消息；A = AI 回复；R1/R2/RN = 第 N 轮；
payload = 每轮请求体；KV cache = 模型服务器为已算内容缓存的键值对；prefill = 对请求
做首次前向计算；MCP = Model Context Protocol；cwd = 当前工作目录；TUI = 终端界面；
SDK = 软件开发工具包。

每轮请求的形态：

```
R1:  [SP, U1]
R2:  [SP, U1, A1, U2]
RN:  [SP, U1, A1, ..., U(N-1), A(N-1), UN]
```

- SP 每轮都在请求头部，每轮恰好一次；历史里没有 SP，所以不会累积成
  `[SP, SP, U1, ...]`。
- RN 的整个 payload 是 R(N+1) payload 的**逐字节前缀**。LLM 服务器比对到前缀相同，
  复用上一轮算好的 KV cache，只增量 prefill 新增的 `[AN, U(N+1)]`。省的是算力，
  请求体每轮照发。

**切换 SP（如 opencode 换 agent）发生在 RN 时：**

```
RN:  [SP_Ask, U1, A1, ..., UN]
```

SP 从第一个字节就与缓存前缀失配，该轮 KV cache 全部作废、从头全量 prefill
（SP_Ask + 全部历史重算一次）。之后只要 SP_Ask 不变，缓存又以它为前缀重新积累。

**工具定义与 SP 同属头部前缀，且只出现一次（以 OpenAI Responses 为例）：**

工具定义不在 input 消息里，而是请求的顶层 `tools` 字段。服务端渲染上下文的顺序固定为：

```
[OpenAI 隐藏 system] → [顶层 instructions] → [tools 工具定义] → [input 消息]
```

- 工具定义天然排在对话消息之前，和 SP 一样每轮发送一次、不进 input，因此不会在
  input 里逐轮叠加；input 只累积对话消息（user / assistant / function_call /
  function_call_output）。
- 虽然每轮都完整发送，LLM 侧的 prefill 对头部是复用的：工具定义不变时，头部前缀
  命中缓存，只增量计算新增消息。
- 工具定义变一个字节（改名字、描述、schema、顺序），失配点在对话之前，其后所有
  内容都无法复用缓存，整轮重算——与换 SP 同效。

一个实际的 opencode 请求（`example_request.md`）同时展示了这套玩法：

```
"store": false                    ← 不用服务端会话存储，客户端每轮回放全部历史
"input": [完整历史消息]            ← 只有对话消息，无工具定义
"tools": [edit, git, glob, ...]   ← 顶层字段，渲染在 input 之前
"prompt_cache_key": "ses_..."     ← 缓存分片键
"x-session-affinity": "ses_..."   ← 路由粘滞，保证请求打到持有缓存的机器
```

opencode 在显式断点协议（Anthropic）上把 `cache_control` 打在最后一个工具定义、
最后一个 system part、最新一条 user 消息上（`packages/llm/src/cache-policy.ts`），
注释原话：Tools live highest in the cache hierarchy——工具在上下文最前段，断点标在
工具尾部即可覆盖 system + tools 整个头部。OpenAI 系协议则完全不打标，交给服务端
隐式断点。

因此 agent 工程的纪律只有一条：**SP 与工具集保持字节级稳定**。pi 为此从默认 prompt
移除日期（保持前缀跨会话可缓存），opencode 按会话设置 `prompt_cache_key`；两者都依赖
"前缀逐字节相同才命中缓存"这一 provider 协议机制（Anthropic `cache_control`、
OpenAI `prompt_cache_key`）。各协议与实现的出处见文末"官方协议参考"。

## 一、pi

### 结构：一个字符串，两个互斥分支

`buildSystemPrompt()`（`packages/coding-agent/src/core/system-prompt.ts`）只有两条分支：

1. **默认分支**：没有自定义 Prompt 时，用内置模板。模板包含：角色定义、`Available tools`
   （每个启用工具一行）、`Guidelines`（工具专属条目 + 全局条目）、pi 文档指针。
2. **自定义分支**：设置了 `SYSTEM.md` 或 `--system-prompt` 时，自定义文本整体替换默认模板。
   `Available tools` 和 `Guidelines` 不会由 pi 拼回来。

没有混合模式：自定义开头 + 自动工具清单不存在，要工具说明就得自己在 SYSTEM.md 里写。

### 固定尾部

两个分支都会在主体之后追加：

| 部分 | 来源 | 默认存在 |
|------|------|----------|
| Append 段 | `APPEND_SYSTEM.md`、`--append-system-prompt` | 无（不自动创建） |
| 项目上下文 | `AGENTS.md` / `CLAUDE.md` / `AGENTS.override.md` | 文件存在时 |
| Skills 段 | 已加载的 skills | 有 skills 且 `read` 启用时 |
| 工作目录 | 会话 cwd | 总是，最后一行 |

### 优先级

自定义 Prompt：`--system-prompt` > 项目 `.pi/SYSTEM.md`（仅项目受信任时加载）>
全局 `~/.pi/agent/SYSTEM.md`。`APPEND_SYSTEM.md` 发现顺序相同。

### 默认模板

```text
You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- <tool>: <一行 snippet>

In addition to the tools above, you may have access to other custom tools depending on the project.

Guidelines:
- <条目>

Pi documentation (read only when the user asks about pi itself, its SDK, extensions, themes, skills, or TUI):
- Main documentation: <readmePath>
- Additional docs: <docsPath>
- Examples: <examplesPath> (extensions, custom tools, SDK)
...

Current working directory: <cwd>
```

内置工具的 snippet（来自各工具文件的 `*ToolSystemPromptContribution`）：

| 工具 | Snippet |
|------|---------|
| `read` | `Read file contents` |
| `bash` | `Execute bash commands (ls, grep, find, etc.)` |
| `edit` | `Make precise file edits with exact text replacement, including multiple disjoint edits in one call` |
| `write` | `Create or overwrite files` |
| `grep` | `Search file contents for patterns (respects .gitignore)` |
| `find` | `Find files by glob pattern (respects .gitignore)` |
| `ls` | `List directory contents` |

工具只在启用且有 snippet 时出现在 `Available tools`。

### Guidelines 的组装顺序

1. 条件条目：仅当 shell 工具（`bash`/`powershell`）启用且 `grep`/`find`/`ls` 全不启用时出现，
   如 `Use bash for file operations like ls, rg, find`。注意：这导致禁用工具有时是**新增**文本。
2. 工具条目：每个启用工具的 `promptGuidelines`，按工具选择顺序。内置的：
   - `read`: `Use read to examine files instead of cat or sed.`
   - `bash`: `You can inspect PI_* environment variables for current model and session details.`
   - `edit`: 4 条（oldText 精确匹配、多位置一次调用、基于原文件匹配、oldText 尽量短）
   - `write`: `Use write only for new files or complete rewrites.`
   - `grep`/`find`/`ls`: 无
3. 恒定条目，与工具无关：`Be concise in your responses`、`Show file paths clearly when working with files`

### 默认 4 工具时的实际 Prompt

```text
You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- read: Read file contents
- bash: Execute bash commands (ls, grep, find, etc.)
- edit: Make precise file edits with exact text replacement, including multiple disjoint edits in one call
- write: Create or overwrite files

In addition to the tools above, you may have access to other custom tools depending on the project.

Guidelines:
- Use bash for file operations like ls, rg, find
- Use read to examine files instead of cat or sed.
- You can inspect PI_* environment variables for current model and session details.
- Use edit for precise changes (edits[].oldText must match exactly)
- When changing multiple separate locations in one file, use one edit call with multiple entries in edits[] instead of multiple edit calls
- Each edits[].oldText is matched against the original file, not after earlier edits are applied. Do not emit overlapping or nested edits. Merge nearby changes into one edit.
- Keep edits[].oldText as small as possible while still being unique in the file. Do not pad with large unchanged regions.
- Use write only for new files or complete rewrites.
- Be concise in your responses
- Show file paths clearly when working with files

Pi documentation (...): <readmePath> / <docsPath> / <examplesPath> 及若干条目

Current working directory: /home/user/myproject
```

### 自定义 SYSTEM.md 覆盖后的样子

`.pi/SYSTEM.md` 内容为 `You are a minimal coding assistant. Write clean, tested code.`，
工具 `read,write,edit,grep,find,ls`（无 bash），无 skills / 上下文 / append：

```text
You are a minimal coding assistant. Write clean, tested code.

Current working directory: /home/user/myproject
```

整个模板消失：角色定义、工具清单、`In addition to the tools above` 行、全部 Guidelines、
pi 文档段。只剩固定尾部。

关键：这只是 Prompt 文本。工具的 JSON schema 仍随请求发送，模型依然能调用这六个工具，
只是收不到任何文字工具说明。要保留自动工具描述，用 `APPEND_SYSTEM.md` 追加而不是替换：

```markdown
You have no execution tool. You cannot run builds, tests, or any command.
Verification happens outside this session. Never claim a test or build passed.
```

### 工具切换会重建 Prompt

`--tools`、`defaultTools`、`setActiveTools` 变更后，系统 Prompt 按新工具集重建：

- 被禁工具丢失 `Available tools` 行和它的 guidelines。
- 条件 shell 条目按新组合重算。
- 禁用 `read` 连 skills 段一起消失（即使有 skills）。
- 恒定条目、pi 文档段、项目上下文、cwd 不受影响。

工具组合变化还可能**新增**文本：bash 在而 grep/find/ls 不在时，出现
`Use bash for file operations like ls, rg, find`。

## 二、opencode

### 架构差异

opencode 没有"一份"系统 Prompt。它由可独立刷新的 Context Source 合成基线；会话中某段
变化时发一条会话中系统消息声明新值。相关术语见其 `CONTEXT.md`（System Context、
Baseline System Context、Mid-Conversation System Message、Context Epoch）。

工具清单**不在**系统 Prompt 里。模型知道工具靠请求里独立的 tools 数组
（name + description + 参数 JSON Schema），与 system 消息是两条通道。

### system 消息的拼接

v1 路径 `packages/opencode/src/session/llm/request.ts` 的顺序：

```
[agent.prompt 或 provider 模板] + env + instructions + mcpInstructions + skills + user.system
```

1. **agent.prompt**：agent 文件（如 `~/.config/opencode/agent/main.md`）正文。若 agent 定义了
   prompt，provider 模板（如 `session/prompt/gpt.txt` 的 107 行）整体被跳过——短路逻辑
   `agent.prompt ?? SystemPrompt.provider(model)`。
2. **env**：`You are powered by the model named ...` + `<env>` 块（工作目录、workspace 根、
   git、平台、日期）。
3. **instructions**：全局 `~/.config/opencode/AGENTS.md` + 项目内 findUp 命中的第一个
   `AGENTS.md`/`CLAUDE.md`（不叠加多级），形如 `Instructions from: <path>\n<content>`。
   也含 `config.instructions` 配置的额外路径/URL。
4. **mcpInstructions**：`<mcp_instructions>` 段，仅当有 MCP server 且有可见工具时。
5. **skills**：`<available_skills>` XML 清单，仅当 `skill` 未被整体 deny 时
   （`session/system.ts:106`）。
6. **user.system**：通常为空。

### 子代理上下文与 AGENTS.md / CLAUDE.md 加载

`Task` 不会把父会话原样传给子代理。它创建带 `parentID` 的新 child session，
`task.prompt` 经 `resolvePromptParts` 后成为该会话的首条 user message；
`task.description` 只用于任务标题和元数据。父会话历史、System Prompt 和工具集不复制。
子代理结束后，输出作为 `Task` 的 tool result 回写父会话。

子代理 System Prompt 的组装顺序与 primary 相同：

```text
子代理 prompt 或 provider 模板
→ env
→ instructions（全局、项目、config.instructions）
→ mcpInstructions
→ skills
→ user.system（Task 普通调用时为空）
```

`AGENTS.md` / `CLAUDE.md` 的加载按以下优先级：

1. 全局：先找 `~/.config/opencode/AGENTS.md`；不存在时再找 `~/.claude/CLAUDE.md`。
   两者只取第一个存在的文件，不叠加。
2. 项目：按 `AGENTS.md` → `CLAUDE.md` → 已废弃的 `CONTEXT.md` 顺序查找。
   每个类别从 child session 的 cwd 向 workspace root 向上查找；某一类别首次命中后停止，
   不会继续叠加更高层级或下一类别。
3. `opencode.json` 中 `config.instructions` 配置的本地路径和 URL，在以上文件后追加。

这些指令属于 System Prompt 的基线内容，不参与工具 permission 过滤，主 Agent 和子代理
都会加载。子代理不会因为 `Task.prompt` 更短而自动获得父 Agent 的指令上下文。

### 工具过滤：permission 硬执行，不靠 Prompt 文字

- 每轮请求前按 `agent.permission + session.permission` 过滤工具注册表
  （`session/llm/request.ts:208` 的 `resolveTools`）。
- `Permission.disabled` 只把 `pattern === "*" && action === "deny"` 视为整体禁用；
  被禁工具的 schema 直接不进请求。
- 规则合并：defaults（`*: allow`）→ 全局用户 permission → agent permission 依次 merge、
  findLast 命中，后写的 deny 压过前面的 allow（`packages/opencode/src/agent/agent.ts`）。
- 两级语义（活体子代理实验证实）：整工具 deny 后模型上报的工具列表里**没有**该工具
  ——是"从请求删除"，不是"可见但调不动"；pattern 级 deny（如 `bash: {"rm *": "deny"}`）
  工具保持可见，执行时抛 `DeniedError`，模型收到 `Tool execution denied.` 的 tool result。
- MCP 工具吃同一套过滤：注册点 `Permission.visibleTools(mcp.tools(), ruleset)`
  （`tool/registry.ts:286`）。`<server>_*: deny` + 逐名 `<server>_<tool>: allow`
  可把模型可见的 MCP 工具面裁到任意子集。
- MCP 工具命名（`mcp/catalog.ts:117-119`）：`sanitize(serverKey) + "_" + sanitize(tool)`，
  仅做非法字符替换，**没有 `mcp_` 前缀**——server key `dep-search` 的工具是
  `dep-search_search_graph`。因此 `mcp_*` 通配匹配不到任何真实 MCP 工具，配了等于没配
  （默认 allow，全部暴露；实验中证实的正是这个现象）。
- 联动的 Prompt 段：
  - `skill` 整体 deny → skills 段整段消失。
  - 某 MCP server 的工具全被 deny → 该 server 的 `<mcp_instructions>` 消失。
  - `task` 被 deny → task schema 消失，挂在 task description 上的
    "Available agent types..." 子代理清单随之消失。
- env、AGENTS.md 不吃 permission，永远在。

### 极简 Code agent 示例

`~/.config/opencode/agent/code.md`：

```markdown
---
name: Code
description: Minimal file-editing agent. No execution, no subagents, no MCP, no plan.
mode: primary
permission:
  bash: deny
  task: deny
  todowrite: deny
  question: deny
  webfetch: deny
  websearch: deny
  lsp: deny
  plan_exit: deny
  # MCP 按 server key 封：<server>_*: deny（mcp_* 无效，见"工具过滤"节）
  execute: deny
---
You write code and design documents only. You have no execution tool: you cannot run builds, tests, or commands. Verification happens outside this session. Never claim a test or build passed.
```

不需要把 allow 写全：全局配置已 allow 的保持，这里只 deny 不需要的。skills 不封，
`skill` 工具保持可用，skills 段保留在 system prompt 中。
deny 之后剩余：read / write / edit（gpt 系模型实际是 apply_patch，见下）/ grep / glob /
skill（目录列表走 read，没有独立 `ls` 工具）。

注意：

- opencode 没有 `ls`/`find` 工具名：目录列表是 `list`（read 读目录），按名找文件是 `glob`。
- gpt 系模型会把 `edit`/`write` 换成 `apply_patch`（`tool/registry.ts:297-300` 的模型分派）。
- `lsp` 只在 `experimentalLspTool` 开启时注册，`plan` 只在 `experimentalPlanMode` 开启时注册；
  deny 它们无害。
- MCP 按 server 维度封：工具名是 `<server>_<tool>`，`<server>_*: deny` 封整个 server，
  逐名 `<server>_<tool>: allow` 例外放行（findLast，allow 写在 deny 后）。
  `mcp_*` 是无效 pattern，见"工具过滤"节。
- 压不掉的 context：env 块、全局 AGENTS.md、agent prompt 本身。项目 AGENTS.md 可用
  `OPENCODE_DISABLE_PROJECT_CONFIG=1` 关闭。

### 该 Code agent 最终看到的东西

system 消息：

```text
You write code and design documents only. You have no execution tool: you cannot run builds, tests, or commands. Verification happens outside this session. Never claim a test or build passed.

You are powered by the model named gpt-5.6-sol. The exact model ID is OpenAI/gpt-5.6-sol
Here is some useful information about the environment you are running in:
<env>
  Working directory: /project/pi
  Workspace root folder: /project/pi
  Is directory a git repo: yes
  Platform: linux
  Today's date: Sun Aug 31 2026
</env>

Instructions from: /root/.config/opencode/AGENTS.md
# OpenCode Rules
...（全局 AGENTS.md 全文）...

Instructions from: /project/pi/AGENTS.md
# Development Rules
...（项目 AGENTS.md 全文）...

Skills provide specialized instructions and workflows for specific tasks.
Use the skill tool to load a skill when a task matches its description.
<available_skills>
  ...
</available_skills>
```

tools 数组（deny 后剩 5 个：read、glob、grep、apply_patch、skill。每个的 description
是仓库 `tool/*.txt` 全文，此处只列概要）：

- `read`：读文件或目录，2000 行上限，offset/limit 分页，可读图片 PDF；
  参数 `filePath`、`offset?`、`limit?`
- `glob`：按 glob 模式找文件；参数 `pattern`、`path?`
- `grep`：正则搜内容；参数 `pattern`、`path?`、`include?`
- `apply_patch`：gpt 系模型的补丁工具，替代 edit/write（模型分派自动换入）；
  参数 `patchText`
- `skill`：按名加载 available_skills 里的技能；参数 `name`

对比总结：pi 把工具清单与部分 guidelines 写进 system prompt 文本；opencode 把工具规则全放在
tools 数组的 description 里，system prompt 永远不含工具清单，禁工具只让 schema 消失。

### example for opencode coder agent

上一节 deny 掉 bash / task / todowrite / question / webfetch / websearch / lsp / plan_exit /
mcp_* / execute 之后，一个专注写代码的 agent 剩余的能力面是 4 个工具（gpt 系模型）：
`read`、`glob`、`grep`、`apply_patch`，外加保留的 `skill`。目录列表没有独立 `ls`，
是 `read` 读目录；按名找文件是 `glob`。

| 工具 | 定位动作 | 入参 | 出参 | 覆盖了什么 |
|------|----------|------|------|-----------|
| `read` | 理解：读文件、看目录结构 | `filePath`（必填，绝对路径）、`offset?`（1 起行号）、`limit?`（默认 2000） | 文件：`<path>` + `<type>file</type>` + `<content>`（每行带行号前缀），结尾提示 `(Showing lines a-b of n. Use offset=... to continue.)`；目录：条目列表，目录带 `/`；图片/PDF：base64 附件；路径不存在时给"Did you mean"候选 | 读源码、追引用、看目录结构（即 list 能力）、读图片/PDF、分页读大文件 |
| `glob` | 定位：按文件名/模式找文件 | `pattern`（必填，如 `src/**/*.ts`）、`path?`（默认 cwd） | 每行一个绝对路径，最多 100 条，超出时提示用更具体 pattern | 找指定名字的文件（即 find 能力），替代 `ls` 式猜测 |
| `grep` | 定位：按内容搜代码 | `pattern`（必填，正则）、`path?`（文件或目录）、`include?`（如 `*.ts`） | `Found N matches`，按文件分组，每行 `Line n: 文本`，最多 100 条，超限提示 | 搜符号定义、调用点、错误串、TODO；全仓库级内容检索 |
| `apply_patch` | 修改：一次完成所有文件变更 | `patchText`（必填，完整 patch 文本） | 每文件的 diff（增删行数），执行后文件落盘 | 新建（`*** Add File`）、修改（`*** Update File`）、删除（`*** Delete File`）、重命名/移动（`*** Move to`），一个 patch 内多文件多操作 |

以 `apply_patch` 为例的 patch 形态：

```
*** Begin Patch
*** Add File: src/hello.ts
+export function hello() {
+  return "hi"
+}
*** Update File: src/main.ts
*** Move to: src/app.ts
@@ function main() {
*** Delete File: src/legacy.ts
*** End Patch
```

这 4 个工具构成完整闭环：

```
任务 → 定位（glob 按名 / grep 按符号）→ 理解（read 读文件、追引用）
     → 修改（apply_patch 增删改移）→ 自查（read 重读改动处，patch 返回 diff）
```

不需要 bash 的能力：文件创建/覆盖/删除/重命名全部由 `apply_patch` 承担。这也是与 pi 的
实质差异：pi 的 `edit`/`write` 不能删文件、不能重命名，opencode 的 gpt 系模型走
`apply_patch`，重构（拆文件、改名、清死文件）闭环成立。

模型分派注意：`apply_patch` 只在 gpt 系模型启用（`tool/registry.ts:297-300`），
非 gpt 模型拿到的是 `edit` + `write`，那套没有 delete/rename，删除重命名缺口重新出现。

仍存在的软缺口（与工具无关，后面讨论）：

1. **git 信息**：opencode 内置工具没有 git 能力，`git log`/`blame` 只能走 bash。
   砍 bash 后失去"这段代码为什么这么写"的历史证据，理解遗留代码的质量会下降。
2. **语法级自查**：没有可执行环境，JSON / 正则等只能目测，产出偶有语法级错误。
3. **库文档**：仅指工作区之外的外部依赖（node_modules、pip 包、第三方 SDK）的官方
   API 文档。本地代码库本身 grep/glob/read 完全覆盖；外部依赖不在工作区内、搜不到，
   而文档里的用法示例、版本差异、已知坑只在网页上，read 只能读实现无法替代。

### opencode 可封禁功能全景与推荐封禁

可封禁项分三类：工具、守卫、遗留 key。

#### 工具类（permission key 即工具名）

| key | 对应工具 | 说明 |
|-----|----------|------|
| `read` | read | 读文件/目录（目录列表即 list 能力） |
| `edit` | edit + write + apply_patch | 三个写工具共用 `edit` 权限 |
| `bash` | bash | shell 执行 |
| `glob` | glob | 按名找文件 |
| `grep` | grep | 内容搜索 |
| `todowrite` | todowrite | todo 列表 |
| `task` | task + 各子代理名 | 总开关；`general`、`explore` 等子代理有独立 key 可单独封 |
| `webfetch` | webfetch | 抓取网页 |
| `websearch` | websearch | 网页搜索 |
| `skill` | skill | 加载 skill；整体 deny 后 system prompt 的 skills 段整段消失 |
| `question` | question | 向用户提问（CLI/desktop/app 下注册） |
| `lsp` | lsp | LSP 语义导航（仅 `OPENCODE_EXPERIMENTAL_LSP_TOOL` 开启时注册） |
| `plan_exit` | plan_exit | plan 模式退出（仅 experimentalPlanMode 开启时注册） |
| `execute` | code-mode | 代码沙箱（仅 experimentalCodeMode 开启时注册） |
| `<server>_<tool>` | MCP 工具 | 名 = sanitize(serverKey)_sanitize(tool)，如 `dep-search_search_graph`；`<server>_*` 通配封整个 server，逐名 allow 例外；`mcp_*` 匹配不到真实工具名 |

#### 守卫类（不是工具，permission 控制行为）

| key | 作用 |
|-----|------|
| `external_directory` | 访问 worktree 之外路径的门禁，read/write/bash 都会检查；deny 即锁死在项目内 |
| `doom_loop` | 模型连续重复同一工具调用达阈值时的确认门禁；deny 则直接报错打断循环 |
| `plan_enter` | 进入 plan 模式的开关 |

#### 遗留 key 与模型分派

- `list` 是旧版独立目录工具残留的 key，现在目录列表并入 `read`，没有工具再检查它。
- gpt 系模型自动把 `edit`/`write` 换成 `apply_patch`（模型分派，非权限控制）；
  非 gpt 模型用 `edit` + `write`，那套没有 delete/rename。

#### 推荐封禁（纯写代码 agent）

```yaml
permission:
  bash: deny          # 无任何执行能力
  task: deny          # 无子代理
  todowrite: deny     # 无 todo
  question: deny      # 不打断
  webfetch: deny      # 无外部文档输入
  websearch: deny
  lsp: deny           # 无 LSP 语义导航（当前收益不明确，直接封）
  plan_exit: deny     # 无 plan 模式切换
  # MCP 按 server 封：<server>_*: deny（如 dep-search_*: deny）；mcp_* 匹配不到真实工具名
  execute: deny       # 无 code-mode 沙箱（本来也只在 experimentalCodeMode 开启且存在 MCP 工具时出现）
```

保留：`read`、`edit`、`glob`、`grep`、`skill`（skills 段保留在 system prompt 里，
技能按需加载，是上下文工程的一部分，不封）。

决策点：

1. `webfetch`：封 = 完全自包含，只写工作区内代码；开 = 可查外部依赖的官方文档。
   纯写库内代码建议封；经常调用外部库建议只放行 `webfetch`、继续封 `websearch`。

不建议动 `doom_loop` / `external_directory`：它们是守卫不是执行通道，默认（ask）即可。
若想进一步收紧，`external_directory: deny` 会把所有读写锁死在 worktree 内。

## 官方协议参考

切换 SP / 工具集导致 prefill 作废的机制来自各 provider 的缓存协议，官方依据如下：

- **Anthropic Prompt Caching**
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
  缓存按请求前缀精确匹配，前缀内容变化则缓存失效；`cache_control: { type: "ephemeral" }`
  标记缓存断点，每请求上限 4 个。opencode 的实现见
  `packages/llm/src/protocols/anthropic-messages.ts`（断点打标）与其 recorded test
  `packages/llm/test/provider/anthropic-messages-cache.recorded.test.ts`
  （第二次完全相同的调用读缓存）。

- **OpenAI Prompt Caching**
  https://platform.openai.com/docs/guides/prompt-caching
  Responses API 按 `prompt_cache_key` + 前缀精确内容命中缓存。opencode v2 runner 每会话
  固定一个 `prompt_cache_key`（`packages/core/src/session/runner/llm.ts`），协议实现见
  `packages/llm/src/protocols/openai-responses.ts`。

- **pi 工程记录**
  - `packages/coding-agent/docs/extensions.md`：激活带 `promptSnippet` / `promptGuidelines`
    的工具会重建 system prompt，"that system-prompt change can invalidate the prefix
    even when the provider supports deferred schemas"。
  - `packages/coding-agent/docs/models.md`：`cacheControlFormat` 与
    `sessionAffinityFormat` 的说明，system prompt、工具定义、最后消息上的 cache 标记策略。
  - `packages/coding-agent/CHANGELOG.md`：从默认 prompt 移除当前日期（"system prompt
    cache invalidation across dates"）、改为稳定 `YYYY-MM-DD` 格式，理由均为保持前缀
    跨 reload / 会话可缓存。

- **opencode 工程记录**
  - `packages/llm/test/cache-policy.test.ts`：缓存断点只标在 system + 最新消息 + 工具上
    的策略测试。
  - `packages/llm/src/providers/openrouter.ts`：`prompt_cache_key` 透传。

结论一致：两个 agent 都不做"只发一次 SP"的优化——请求体每轮完整发送；缓存命中与否由
provider 按前缀字节比对决定，前缀一变（换 SP、改工具定义）即全量 prefill 重来。
