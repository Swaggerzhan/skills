# agrep（Go 版）设计文档

agrep 是 opencode 内置 grep 的克隆 + 必填参数 `intent`（声明搜索目的，仅
用于记录）。实现分两层：`.opencode/tool/agrep.ts` 为稳定壳（参数 schema +
spawn），全部重逻辑在 Go 二进制 `otools/cmd/agrep`。更新 = 替换二进制文件
（路径由 `OPENCODE_OTOOLS_AGREP_BIN` 指定），壳保持稳定；同时卸载 mysql2 npm
依赖的部署负担。

## 1. 结构

- **壳**：描述与参数 schema 原样保留（LLM 侧契约零变化）；职责只剩解析
  `path`、组装 argv、spawn、透传结果。
- **Go 二进制**：每次调用一个新进程（`os/exec`），进程即生命周期：替换
  二进制下一次调用即生效；MySQL 连接随每次调用重建，DB 恢复后记录随之
  恢复。
- 二进制的下游：`rg` 与 `codebase-memory-mcp`（均经 PATH 查找）、
  `~/.config/otools/agrep.jsonc`（配置）、MySQL（记录）、opencode.log
  （WARN）。
- 仓库根的 `otools/` 为纯 Go module（与 `.opencode/` 部署面无关）；Go 源码
  随仓库走，二进制由各机器本地 `go build` 产出。

## 2. 接口契约

### 2.1 壳 → 二进制（argv flags）

```text
--pattern=<>       rg 搜索词
--include=<>       文件 glob
--intent=<>        搜索目的
--path=<>          搜索根目录，绝对路径
--session-id=<>    会话 ID，记录主键之一
--message-id=<>    消息 ID（轮次标识），记录主键之一
--agent=<>         调用方 agent
```

壳一律用 `--name=value` 连写：值以 `-` 开头也不会被 flag 包误解析。

`path` 在 LLM 侧为可选 arg，壳在 spawn 前解析：`args.path ?? ctx.directory`，
相对路径按 `ctx.directory` resolve，二进制收到的永远是绝对路径。其余字段
壳原样转发。

### 2.2 二进制 → 壳（stdout + 退出码；flag 解析错误除外）

输出只有一个形态：string。

- 退出码 0：stdout 全文即结果字符串，壳原样 `return`。
- 退出码 1（参数校验、搜索失败）：stdout 全文即错误消息，壳
  `throw new Error(stdout)`，回喂模型——与现版参数校验抛错同一路径。
- flag 解析失败（未知 flag，退出码 2）：flag 包默认行为，usage 写
  stderr，壳 merge 两路流后 throw。

### 2.3 配置（`~/.config/otools/agrep.jsonc`）

```jsonc
{
  // 记录配置；文件缺失、解析失败或任一字段缺失 → 记录静默关闭（WARN 一行）
  "mysql": {
    "endpoint": "host:3306", // 无端口默认 3306
    "username": "...",
    "password": "...",
    "database": "..."        // 库须预先存在，工具只建表
  },
  "proto_gen_file_filter": true // 可选；默认 true 启用 protobuf 生成代码过滤（排除与提示）；false 手动关闭
}
```

JSONC 用真 tokenizer 解析：字段值（如密码）可能含注释字符，剥注释会误伤
字符串内容。

二进制路径由环境变量 `OPENCODE_OTOOLS_AGREP_BIN` 指定，缺省 `~/.local/bin/agrep`。

## 3. 工具规格（LLM 侧）

壳保留现版 description 与参数 describe 文案（重写时从现 `agrep.ts` 逐字
复制）。参数与校验：

- `pattern`、`include`、`intent` 必填；`path` 可选。
- `include` 禁止裸 `"*"`。
- 校验失败：所有问题合并为一条错误消息，记一条错误行（§8）后走 §2.2
  失败路径回喂模型。

## 4. 搜索

rg 调用（cwd = `--path`）：

```text
rg --no-config --json --hidden --no-messages --no-ignore-parent
   --glob=<include>
   --glob=!<§5 各生成文件模式>     # proto_gen_file_filter 启用时
   --glob=!**/.git/**
   -- <pattern> .
```

`--no-ignore-parent`：不加载 `--path` 祖先目录的 ignore 规则；搜索树自己的
.gitignore 照常生效。

- 上限 100 条；单行超 2000 字符截断（截断点超过 70% 处存在换行时在该
  换行处截）。
- 匹配按文件 mtime 降序排序，按文件分组输出：

```text
Found 2 matches

path/to/file:
  Line 12: matched text
```

- 达 100 条上限时末尾追加 `(Results truncated. Consider using a more
  specific path or pattern.)`；0 结果输出 `No files found`。
- rg 的 stderr 非空且退出码非 0，或退出码为 2 → 搜索失败，走 §2.2 失败
  路径。
- rg stdout 累积超 1MB 时 kill rg。

## 5. protobuf 生成代码过滤

排除清单（作为 rg 排除 glob，与 `!**/.git/**` 同级，`proto_gen_file_filter`
启用时每次搜索都加）：

- C/C++：`*.pb.h` `*.pb.cc` `*.grpc.pb.h` `*.grpc.pb.cc` `*.pb.validate.h`
  `*.pb.validate.cc`
- Python：`*_pb2.py` `*_pb2.pyi` `*_pb2_grpc.py`
- Rust：`*.pb.rs`
- Go：`*.pb.go` `*_grpc.pb.go` `*.pb.gw.go` `*.pb.validate.go`
- JS/TS：`*_pb.js` `*_pb.d.ts` `*_grpc_pb.js` `*_grpc_pb.d.ts`

提示：搜索完成后，从 `include` 提取后缀（一层 brace 展开，`*.{h,cc}` →
h/cc），取与上表相关的模式，探测这类文件在搜索树下是否真实存在
（`rg --files` 纯文件名扫描，5s 超时，拿到首行即 kill，探测失败不加提示）。
存在则产出提示（拼接规则见 §7）：

```text
[proto_gen_filter]: generated files like "<探测到的文件名>" filtered out; do not read generated code — the .proto is enough.
```

## 6. dep_search 提示

- **触发**：`include` 提取出的后缀与代码后缀表有交集：

```text
c h cc cpp cxx hh hpp hxx cu cuh m mm go rs zig nim d v sv
js jsx mjs cjs ts tsx mts cts vue svelte py rb php lua pl pm r jl ex exs erl hrl
java kt kts scala groovy cs fs vb swift dart hs ml mli clj cljs elm
sh bash zsh sql proto
```

- **项目判定**：exec `codebase-memory-mcp cli list_projects --limit 100`
  （stdout 即 payload JSON，超时 10s），取 `projects` 的 `name/root_path`，
  按路径边界包含搜索目录的最长 root 匹配。
- **注入预算**：每 session 对同一 project 最多注入 3 次，计数落
  `agrep_inject_records`（§8）：先条件 UPDATE
  （`SET inject_count = inject_count + 1 WHERE inject_count < 3`，行锁原子）
  抢名额；影响行数为 0 则 INSERT 新行，撞 `ER_DUP_ENTRY` 即名额已满。
  MySQL 记录关闭时注入随之关闭（预算依赖 DB）。
- **提示文本**（拼接规则见 §7）：

```text
[dep_search]: this code is indexed. For faster structural code search, use the dep_search_* tools with project "<name>".
```

- **失败**（CLI 缺失/超时/非零退出/输出不可解析）→ WARN 一行，不加提示，
  搜索与记录照常。

## 7. 输出组装（Reminder 块）

最终 stdout = rg 输出 + 可选的 Reminder 块。§5、§6 各产出至多一条提示，
按 proto_gen_filter 先、dep_search 后的顺序拼接。完整形态：

```text
<rg 输出>

Reminder:
[proto_gen_filter]: generated files like "addressbook.pb.h" filtered out; do not read generated code — the .proto is enough.
[dep_search]: this code is indexed. For faster structural code search, use the dep_search_* tools with project "brpc".
```

逐字节规则（与现版 `result.output + "\n\nReminder:\n" + hints.join("\n") + "\n"` 一致）：

- 块头固定为 `Reminder:` 一行；触发哪条拼哪条，每条一行。
- 块与 rg 输出之间空一行（`\n\n`），块尾带一个换行。
- **两条都未触发 → Reminder 块整体不出现**，stdout 就是纯 rg 输出，一个
  字符都不多加。

## 8. 记录（MySQL）

驱动 `github.com/go-sql-driver/mysql` + `database/sql`。建连后执行两张表的
`CREATE TABLE IF NOT EXISTS`：

```sql
CREATE TABLE IF NOT EXISTS agrep_records (
  session_id   VARCHAR(64)     NOT NULL,
  message_id   VARCHAR(64)     NOT NULL,
  turn_id      INT UNSIGNED    NOT NULL,
  created_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  agent        VARCHAR(64)     NOT NULL,
  pattern      TEXT            NULL,
  path         VARCHAR(1024)   NOT NULL,
  include      VARCHAR(255)    NULL,
  intent       TEXT            NOT NULL,
  matched_files  INT             NULL,
  matched_lines  INT             NULL,
  truncated    TINYINT(1)      NULL,
  output_text  MEDIUMTEXT      NULL,
  error        TEXT            NULL,
  PRIMARY KEY (session_id, message_id, turn_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agrep_inject_records (
  session_id     VARCHAR(64)  NOT NULL,
  project_name   VARCHAR(255) NOT NULL,
  inject_count   INT UNSIGNED NOT NULL DEFAULT 0,
  inject_content TEXT         NULL,
  PRIMARY KEY (session_id, project_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

- **插入时机**：output 组装完成后、写 stdout 前；插入内容即最终 output
  （含 Reminder 块）。insert 失败只记 WARN，本次搜索结果照常返回。
- **主键 `(session_id, message_id, turn_id)`**：`turn_id` 在
  `(session_id, message_id)` 内从 1 递增，标识一条 message 内的第几次
  调用。InnoDB 无分组自增，插入时
  `INSERT ... SELECT COALESCE(MAX(turn_id),0)+1 ... WHERE session_id=? AND message_id=?`
  计算，撞 `ER_DUP_ENTRY` 即重试（并发窗口极小）；一条 message 并发多次
  调用各自成行。
- **错误行**：参数校验失败记一行——`error` 列填合并后的消息，
  `matched_files/matched_lines/truncated/output_text` 为 NULL，`intent` 存原始值（含空串）。
- **降级**：配置缺失 / DB 不可达 / 建表失败 → 本调用内记录关闭。所有
  WARN 均为向 `${XDG_DATA_HOME:-~/.local/share}/opencode/log/opencode.log`
  追加一行 `level=WARN service=agrep`。
- `created_at` 取 DB 服务器时间（`CURRENT_TIMESTAMP(3)`），多机器写入统一
  时钟。

## 9. 模块布局

```text
.opencode/tool/
└── agrep.ts          # 壳（重写，此后稳定）
otools/               # 仓库根，Go module
├── go.mod            # module otools（已初始化）
└── cmd/
    └── agrep/        # main 包
```

## 10. 边界情况

- **二进制缺失/不可执行**：spawn 失败，壳 throw 错误文本，模型看到失败。
- **配置缺失或字段不全**：记录关闭、过滤保持默认开启，WARN 一行。
- **项目列表缓存**：进程即生命周期，每次代码搜索 spawn 一次 CLI（10s 超时
  封顶，daemon 热时为毫秒级）；实测成为热点再加磁盘缓存。
- **MySQL 每调用建连**：TCP + 认证握手在局域网为毫秒级；建表语句为
  `IF NOT EXISTS` 空转。
- **abort**：壳发 SIGTERM；记录是旁路，中断时未完成的记录行丢弃即可。
