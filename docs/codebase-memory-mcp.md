# codebase-memory-mcp：依赖图谱查询

本文描述如何安装 codebase-memory-mcp 并接入 opencode，让 agent 能查询本库之外依赖的
代码图谱。内容自包含，不依赖任何本机路径。

## 是什么

codebase-memory-mcp（上游：https://github.com/DeusData/codebase-memory-mcp）把代码库
索引成持久知识图谱（函数、类、调用链），通过 MCP 向 agent 暴露只读查询工具。对
"这个符号在哪定义 / 谁调用了它 / 读一下这个函数"这类依赖查询，比 grep 逐行扫文本
更高效：图查询直接返回结构化结果，按调用关系去重排序，还能多跳追溯调用链。

局限：C++ 模板/宏场景图可能漏边；解析失败的文件内容不在图中。下穷举结论
（"没有人调用 X"）之前，必须先用 `check_index_coverage` 核查涉及路径的覆盖状态，
有缺口就回退 grep 直接查源码。

## 安装

### 1. 获取并构建

```bash
git clone https://github.com/DeusData/codebase-memory-mcp.git
cd codebase-memory-mcp
./scripts/build.sh
```

产物：`build/c/codebase-memory-mcp`。需要 C 编译器和 zlib。

### 2.（可选）排除文档文件

`.md` / `.mdx` / `.rst` 默认会作为图节点进索引。只想要代码：在**每个**待索引仓库的
根目录放一个 `.cbmignore` 文件，内容：

```gitignore
*.md
*.mdx
*.rst
```

它只被索引器读取，对 git 无影响；下一次索引时生效。

### 3. 启动常驻 daemon

```bash
./build/c/codebase-memory-mcp daemon start
```

后续索引命令和查询会复用该 daemon，明显更快。查看状态：`daemon status`；
结束后关闭：`daemon stop`。所有进程必须使用同一个二进制和同一个 cache 根
（默认 `~/.cache/codebase-memory-mcp`）。

### 4. 索引依赖仓库

对每个依赖的源码仓库执行一次（以 gflags 为例）：

```bash
./build/c/codebase-memory-mcp cli index_repository --repo-path /path/to/gflags --mode full --name gflags
```

- `--name` 必须加：不加时 project 名从完整路径派生，`/path/to/gflags` 会变成
  `path-to-gflags`，与预期不一致。
- 命令退出并返回索引状态（含节点/边数量）才算完成；返回 `degraded` 时不要当作
  完整索引使用。
- 静态库（版本固定的第三方依赖）：手动重建索引即可，库版本升级时重跑一次。
- 正在开发的项目：同样另建一个 project，可开启 watcher 自动增量刷新
  （`config set auto_watch true`，默认开启）。
- 一个 cache 可存多个 project，查询时按 `project` 参数隔离，不会混图。

前提：索引的源码版本必须和实际编译链接的头文件/库版本一致，否则 agent 看到的
API 不是你真正链接的 API。

## 接入 opencode

在 opencode 配置的 `mcp` 字段中注册（本项目使用的 server key 是 `dep_search`）：

```jsonc
"mcp": {
  "dep_search": {
    "type": "local",
    "command": ["/path/to/codebase-memory-mcp", "--tool-profile=analysis"],
    "enabled": true
  }
}
```

- `--tool-profile=analysis`：服务端只声明 12 个只读工具，4 个写工具（重建索引、
  删项目、改 ADR、写 trace）从工具列表剔除，对模型不可见。
- opencode 启动时拉起该进程，通过 stdin/stdout 按 MCP 协议通信；配置只有整服务器
  级别的开关，按工具裁剪靠下面的 permission 实现。修改后重启 opencode 生效。

### 工具命名（关键）

opencode 里 MCP 工具名 = `sanitize(serverKey) + "_" + sanitize(tool)`，没有 `mcp_`
前缀。server key 为 `dep_search` 时，工具是 `dep_search_search_graph` 这种形态。
**`mcp_*` 是匹配不到任何工具的无效 pattern**——配了等于没配（默认 allow，全部暴露）。

### 按 agent 裁剪工具面

permission 的整工具 deny 会把工具从模型视野里彻底删除（不是"可见但调不动"）。
规则按 findLast 求值：宽规则在前，逐名 allow 在后。本项目的 Coder / CodeLeader
agent 配置：

```yaml
permission:
  dep_search_*: deny                          # 默认全封
  dep_search_list_projects: allow             # 以下 6 条例外放行
  dep_search_search_graph: allow
  dep_search_search_code: allow
  dep_search_get_code_snippet: allow
  dep_search_trace_path: allow
  dep_search_check_index_coverage: allow
```

想放行的工具变了，就在 deny 行之后补一条 `dep_search_<tool>: allow`，重启生效。
该机制的源码出处见本仓库 `docs/agent_rule.md` 的"工具过滤"一节。

## 怎么用

放行的 6 个工具：

| 工具 | 用途 |
|---|---|
| `dep_search_list_projects` | 列出已索引的 project，返回值里的 `name` 就是其他工具的 `project` 参数 |
| `dep_search_search_graph` | 找符号定义：`name_pattern`（正则）或 `query`（全文），结果含 qualified_name |
| `dep_search_search_code` | 图增强 grep：文本命中归并到所属函数，定义排前、test 排后；只覆盖被索引的文件 |
| `dep_search_get_code_snippet` | 按 qualified_name 读符号源码（先用 search_graph 拿到 qn） |
| `dep_search_trace_path` | `direction=inbound` 查全部调用方（改签名前必做），`outbound` 查它调谁 |
| `dep_search_check_index_coverage` | 核查路径/目录的索引覆盖（`parse_partial` / `skipped`） |

典型流程：

```
search_graph 找定义拿到 qualified_name
→ get_code_snippet 读源码
→ 要改它之前 trace_path(direction=inbound) 拿调用方列表
→ check_index_coverage 确认涉及文件没有解析缺口，有缺口用 grep 补查
```

纪律只有一条：图结果是 best-effort。"没找到"不等于"不存在"——下否定/穷举结论前
先 `check_index_coverage`，`parse_partial` 或 `skipped` 的文件直接读源码。

未放行及原因：`query_graph` / `get_graph_schema`（手写 Cypher，token 开销大）、
`get_architecture` / `detect_changes`（本项目暂不需要）、`index_status` /
`compare_graphs`（索引运维用途）。

## 备选：单工具包装器

本仓库 `backup_tool/dep_search.ts` 是一个自定义 tool 包装器（单工具 + action 分发，
走 CLI 一次性模式），可把 agent 可见的工具面从 6 个收敛到 1 个 `dep_search`。
当前未启用；需要时挪回 `.opencode/tool/`，并把 agent 权限换成
`dep_search: allow` + `dep_search_*: deny`。
