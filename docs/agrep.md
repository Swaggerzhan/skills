# agrep 设计文档

agrep = opencode 内置 grep 的克隆 + 第 4 个必填参数 `intent`（自由文本，声明本次
搜索的目的）。intent 不改变搜索行为，仅用于记录；记录落 MySQL，全局生效，
覆盖所有 session。代码搜索且目录命中已索引项目时，输出末尾追加 dep_search
提示（§6）。

## 1. 安装与配置

### 1.1 环境变量（4 个必填）

写入 shell rc 或 opencode 启动环境，与现有 `OPENCODE_*_KEY` 同方式：

| 变量 | 含义 | 说明 |
|---|---|---|
| `OPENCODE_AGREP_MYSQL_ENDPOINT` | `host:port` | 按最后一个 `:` 切分；无端口默认 3306 |
| `OPENCODE_AGREP_MYSQL_USERNAME` | 账号 | 需有所在库的 CREATE 权限（表自动建） |
| `OPENCODE_AGREP_MYSQL_PASSWORD` | 密码 | |
| `OPENCODE_AGREP_MYSQL_DATABASE_NAME` | 库名 | **库须预先存在，工具不建库** |

另有一个可选开关：`OPENCODE_AGREP_NO_FILTER`（非空且非 `0`/`false` 即生效）——
关闭内置的 protobuf 生成代码过滤（§6），默认开启。

缺库先建：

```sql
CREATE DATABASE your_db CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

表不用手工建：主表 `agrep_records`、注入预算表 `agrep_inject_records` 均在首次
连接时 `CREATE TABLE IF NOT EXISTS` 自动建（固定表名，不配 env——曾有过的
`OPENCODE_AGREP_MYSQL_TABLE_NAME` 已删除：可配置表名没有实际收益，漏配还会
把记录功能整体静默关掉）。

### 1.2 依赖安装（mysql2）

```bash
cd ~/.config/opencode-config/.opencode && npm install mysql2
```

必须在**部署 clone** 的 `.opencode/` 下显式安装，原因：

- 模块解析按工具文件的 realpath 上溯；`~/.config/opencode/tool` 是指向 clone
  的 symlink，装在仓库源码目录或 `~/.config/opencode/` 下都无效；
- `npm -g` 全局安装不在 ESM 解析路径上；
- `.opencode/.gitignore` 不提交 `package.json`，clone 里那份由 opencode 自动
  生成（仅含 `@opencode-ai/plugin`），裸 `npm install` 不会装 mysql2，必须
  显式带包名；每台新机器部署后都需执行一次（或后续扩展 install 脚本自动补
  依赖）。

缺包不致命：mysql2 为调用时动态 `import()`，缺失只关闭记录并记 WARN，
不会拖垮工具注册。

### 1.3 部署与权限

- `install_opencode_config.sh` 已把 `.opencode/tool/` symlink 到
  `~/.config/opencode/tool/`，仓库内即全局生效，所有 session 可用。
- `opencode.jsonc` 的 `permission` 含 `"agrep": "allow"`；七个 agent
  （main/scout/insight/coder/codeleader/codebuilder/general）均为
  `grep: deny` + `agrep: allow`。**注意**：`"*": deny` 的 agent 里自定义工具
  必须显式列条目，否则对模型不可见（2026-09-12 踩坑）。

### 1.4 验证

重启 opencode 后触发一次 agrep，然后：

```sql
SHOW TABLES;  -- 应有 agrep_records / agrep_inject_records
SELECT * FROM agrep_records ORDER BY seq DESC LIMIT 1;
```

未生效时查 `${XDG_DATA_HOME:-~/.local/share}/opencode/log/opencode.log` 里
`level=WARN service=agrep` 的行，会写明原因（缺 env / 连接失败 / 权限不足）。

## 2. 工具规格（已核实 opencode dev 分支源码）

- 参数：`pattern`（必填）、`path`（可选）、`include`（**必填**）+ `intent`（必填）。
- 空 `intent` / 空 `include`（含纯空白）→ 抛错，错误文本回喂模型重写调用——与内置
  grep 对空 `pattern` 的处理模式相同（`throw new Error("pattern is required")`）。
  多个必填缺失时合并为一条错误。
- `include` 强制非空且**禁止裸 `"*"`**：迫使模型显式声明搜索的文件范围（范围
  本身是研究语料），不留"全量搜索"逃逸口；描述与参数 describe 均写明拒绝 `*`，
  违规按参数校验失败处理（记录错误行 + 抛错回喂）。`include` 列保持
  NULL-able（供错误行使用）。
- description = grep 原文 bullet（include 条目改为 REQUIRED 并写明禁止裸
  `"*"`）+ intent 必填说明（英文短语、几个词、附示例）。
- 搜索行为与 grep 一致：同样的 rg 调用
  （`rg --no-config --json --hidden --no-messages [--glob=include] --glob=!**/.git/** -- <pattern> .`）、
  100 条上限、单行 2000 字符截断、相同的输出排版。两个出口处与 grep 不同：
  记录逻辑不改变搜索内容本身；搜索内置排除 protobuf 生成代码，且输出末尾可能
  追加 Reminder 提示块（§6）。

## 3. 存储选型：MySQL

结论：**好整**。自定义工具可以 import npm 包（官方示例即 import
`@opencode-ai/plugin`），`mysql2` 是纯 JS 驱动、无原生绑定，预期在 opencode
运行时可用（实现时验证，见 §8）。

相比 JSONL，MySQL 换来的东西：多 session/多机器集中写入、SQL 直接做 intent
分布统计与会话回放、不用自己管 rotation。代价是引入一个网络依赖：DB 不可用时
记录静默关闭（§5），搜索功能不受影响——记录是纯旁路。

连接管理：模块加载时即发起连接（fire-and-forget），首次调用复用同一 promise；
建池后执行两张表的 `CREATE TABLE IF NOT EXISTS`。连接失败 → 本进程内记录关闭，
不重试。标识符反引号拼接（私有环境，不做注入防护）；行数据用 `mysql2` 占位符
传值。

## 4. 表结构

主表：

```sql
CREATE TABLE IF NOT EXISTS agrep_records (
  session_id   VARCHAR(64)     NOT NULL,
  seq          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  created_at   DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  agent        VARCHAR(64)     NOT NULL,
  directory    VARCHAR(512)    NOT NULL,
  pattern      TEXT            NOT NULL,
  path         VARCHAR(1024)   NOT NULL,
  include      VARCHAR(255)    NULL,
  intent       TEXT            NOT NULL,
  matches      INT             NULL,
  truncated    TINYINT(1)      NULL,
  output_text  MEDIUMTEXT      NULL,
  error        TEXT            NULL,
  PRIMARY KEY (session_id, seq),
  KEY idx_seq (seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

注入预算表：

```sql
CREATE TABLE IF NOT EXISTS agrep_inject_records (
  session_id     VARCHAR(64)  NOT NULL,
  project_name   VARCHAR(255) NOT NULL,
  inject_count   INT UNSIGNED NOT NULL DEFAULT 0,
  inject_content TEXT         NULL,
  PRIMARY KEY (session_id, project_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

设计依据：

- **主键 `(session_id, seq)`**：session_id 单独不唯一（一个 session 有多次 agrep
  调用），复合主键让同一 session 的记录在 InnoDB 聚簇索引上物理相邻、按 seq
  有序——"回放某 session 的 agrep 轨迹"是一次范围扫描。InnoDB 要求
  AUTO_INCREMENT 列必须是某个索引的首列，PK 中 seq 在第二位不满足，故加
  `KEY idx_seq (seq)`。
- **intent 不建索引**：自由文本、非枚举，LLM 用词高基数低重复，二级索引无
  意义。v1 对 intent 的分析走全表扫描 + `GROUP BY`（数据量小，可接受）；
  若将来数据量大需要检索，再加 `FULLTEXT(intent)`（InnoDB 支持自然语言全文
  索引）或直接换外部分析工具，schema 不需要变。
- **`output_text MEDIUMTEXT`**：单条 output 最坏超 64KB（100 行 × 2000 字符 +
  路径头），TEXT 存不下；MEDIUMTEXT 上限 16MB，够用。
- **`error` 非空即失败调用**：空 intent 拒绝、rg 执行失败都记录（intent 为空时
  intent 列存原始空串）；此时 `matches/truncated/output_text` 为 NULL。失败调用
  是模型行为数据的一部分，不丢。
- **`created_at` 用 DB 服务器时间**：多客户端写入时统一时钟，免去各机器时区
  校准。
- **`COLLATE utf8mb4_bin`**：pattern/intent 区分大小写，避免统计时
  `Permission` 与 `permission` 被合并。
- `matches` 对应 grep metadata 的 matches（0 结果时为 0，不是 NULL）；
  `agent/directory` 取自工具 ctx。
- **`path` 记解析后的实际搜索目录**（LLM 未传时为当前工作目录，与 grep 的
  缺省行为一致），因此 NOT NULL；`include` 由工具强制非空，NULL 只出现在
  参数校验失败的错误行。

典型查询：

```sql
-- 回放一个 session 的 agrep 轨迹
SELECT seq, created_at, intent, pattern, matches FROM agrep_records
 WHERE session_id = 'ses_...' ORDER BY seq;

-- intent 用词分布（校准未来枚举设计的原料）
SELECT intent, COUNT(*) AS n FROM agrep_records
 WHERE error IS NULL GROUP BY intent ORDER BY n DESC LIMIT 50;

-- dep_search 注入次数（注入文本随 output_text 落库）
SELECT COUNT(*) FROM agrep_records
 WHERE output_text LIKE '%[dep_search]%' AND error IS NULL;

-- 各 session 的注入预算消耗
SELECT * FROM agrep_inject_records ORDER BY inject_count DESC;
```

## 5. 记录行为

- **静默降级**：记录是旁路，绝不影响搜索。env 未配置 / DB 不可达 / 建表失败 →
  记录功能在本进程内关闭（不重试）；insert 失败 → 跳过该行。两者都只向
  opencode 日志（`${XDG_DATA_HOME:-~/.local/share}/opencode/log/opencode.log`）
  追加一条 `level=WARN service=agrep` 单行，不向模型报错。
- **插入时机**：grep 输出组装完成后、返回前插入；记录的是 execute 返回前的
  完整 output。insert 失败不影响本次搜索结果的返回。
- **并发**：多个 opencode 进程同时插入由 InnoDB auto_increment 天然保证安全，
  无需客户端锁。

## 6. 输出注入（Reminder 块）

两种提示按序拼成一个块追加在 rg 输出之后；**都不触发则整块不加**：

```
<正常 rg 输出>

Reminder:
[proto_gen_filter]: generated files like "addressbook.pb.h" are filtered out; you should not read generated code — the .proto definition is enough.
[dep_search]: this code is indexed. For faster structural code search, use the dep_search_* tools with project "brpc".
```

### 6.1 protobuf 生成代码过滤（内置，LLM 不可控）

- **排除清单**（收紧到 c/cpp/py/rust/go/js/ts）：rg 调用无条件追加排除 glob
  （与硬编码 `!**/.git/**` 同级，include 白名单先生效、黑名单后生效）：
  - C/C++：`*.pb.h` `*.pb.cc` `*.grpc.pb.h` `*.grpc.pb.cc` `*.pb.validate.{h,cc}`
  - Python：`*_pb2.py` `*_pb2.pyi` `*_pb2_grpc.py`
  - Rust：`*.pb.rs`（约定俗成；prost 本身无文件名标记）
  - Go：`*.pb.go` `*_grpc.pb.go` `*.pb.gw.go` `*.pb.validate.go`
  - JS/TS：`*_pb.js` `*_pb.d.ts` `*_grpc_pb.js` `*_grpc_pb.d.ts`
  - 这些都是双后缀（真实扩展名仍是 `.h`/`.go`），`*.h` 这类 include 照样会
    命中它们——不过滤必然爆上下文。Java/C#/ts-proto 无文件名标记，不做。
- **开关**：默认开启；`OPENCODE_AGREP_NO_FILTER=1` 彻底关闭（排除与提示都关）。
- **提示触发**：仅当与本次 include 后缀相关的生成文件**真实存在**于搜索树下
  才注入（`rg --files` 存在性探测，纯文件名扫描、5s 超时、拿到首行即 kill，
  探测失败静默不加）。提示中引用探测到的真实文件名，措辞直述"不该读生成
  代码，读 .proto 就够"。

### 6.2 dep_search 提示

- **触发条件**：`include` glob 提取出的后缀（支持一层 brace 展开，
  `*.{h,cc}` → h/cc；无后缀文件名如 `Makefile` 不触发）与内置代码后缀表
  （c/h/cc/cpp/hpp/go/js/ts/py/rs/java/…）有交集。
- **项目判定**：spawn `codebase-memory-mcp cli list_projects --limit 100`
  （默认 stdout 即裸 payload JSON——`cli_print_mcp_result` 解包
  `content[0].text`；`--json` flag 反而是完整 envelope，不用；进度/日志噪音
  全走 stderr，且非 tty 时自动关闭），取 `projects` 的 `name/root_path`，
  按路径边界包含搜索目录的**最长匹配**（同
  `hook_augment.c::ha_registry_project_for_path` 语义）。错误走
  stderr + 非零退出。
- **缓存**：项目列表进程内缓存 60s；CLI 超时 10s（容忍 daemon 冷启动）。
- **注入预算**：每个 session 对同一 project 最多注入 3 次，持久化在
  `agrep_inject_records`（DDL 见 §4）。计数用条件 UPDATE 抢名额
  （`SET inject_count = inject_count + 1 ... WHERE inject_count < 3`，行锁
  原子），避免并发超发；新行 INSERT 撞 `ER_DUP_ENTRY` 即名额已满。计数落库
  而非进程内存：重启不丢、共享 DB 的多机器一致。MySQL 不可用（记录已禁用）
  时注入同样静默关闭——预算依赖 DB。subagent 的 task 是独立 session，有独立
  预算。
- **失败语义**：与记录一致——CLI 缺失/超时/非零退出/输出不可解析 → 一条
  `level=WARN service=agrep` 日志，不注入，搜索与记录不受影响。无匹配项目
  属正常情况，静默跳过。

## 7. 单测

- `tool/` 目录下每个 `.ts` 都会被 opencode 注册为工具，**测试文件不能放进
  `tool/`**；测试放仓库 `tests/` 下，`bun test` 直接跑 TS。
- 纯函数（`extractExts`、`activeGenPatterns`、`resolveSearchRoot` 等）以
  named export 导出供测试 import；测试 setup 把 `XDG_DATA_HOME` 指向临时目录，
  避免模块加载的 DB init 把 WARN 写进真实 opencode.log。
- `search()` 可对 fixture 目录做真 rg 集成测试；MySQL / codebase-memory-mcp
  CLI 路径不做单测，走部署后实测（§8 清单）。

## 8. 实现时验证清单

1. ~~`mysql2` 在 opencode 运行时（Bun）内可 import~~ → 已改为调用时动态
   `import()`：包缺失不会拖垮工具注册（2026-09-12 事故：`Cannot find module
   'mysql2/promise'` 在 ToolRegistry 加载期炸掉所有 session），缺包只关闭记录
   并记 WARN。装包后可用性待实测。
2. ~~全局工具经 symlink 加载时 npm import 的 node_modules 解析路径~~ → 已确认
   按 realpath 上溯（报错信息中模块路径为 clone 真实路径），安装位置见 §1.2。
3. 自定义工具返回值是否经过 opencode 内部 `truncate.output` 管线（内置工具会，
   超限改写到 outputPath）——决定表中 `output_text` 与模型最终所见是否一致，
   实现时实测一次；记录始终以 execute 返回前为准。
