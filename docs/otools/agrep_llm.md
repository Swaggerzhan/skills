# agrep LLM 协助者（探索文档）

探索性设计，不进当前实现；当前实现以 `agrep_new.md` 为准。本文记录"在
agrep 内引入一个内部 LLM 协助者"的方案：搜索结果超阈值时，让一个（通常
较差的）模型借助 cbm 工具判断并改写返回值，保持主上下文干净。动机不是省
token，是用内部模型的 token 换主 agent 的效率。

## 1. 触发与管线位置

管线（与 `agrep_new.md` 同一管线，第 4 步为本设计插入点）：

```text
1. rg 搜索（pb 生成文件排除 glob 已生效）
2. pb 过滤探测 → Reminder 行备好，暂不追加
3. cbm list_projects → 命中已索引项目则备好 dep_search Reminder 行
4. matches > threshold（默认 75，可配）且配置存在 → 启动协助者 loop
5. 协助者产出最终匹配块；before/after 落库
6. Reminder 追加（含协助者来源标记）→ 写 agrep_records → stdout
```

吐给协助者的 input 是纯 rg 匹配块（`Found N matches...` 拼装结果），不含
任何 Reminder 行——此时 Reminder 尚未追加，天然满足。

`threshold` 比较基准是 `matches` 条数（"Found N matches" 的 N），空行与
文件头行是排版产物，不参与计数。默认 75：75 条匹配约 10KB+/3k tokens，
过滤收益抵得过一次 LLM 往返的秒级延迟；50 以下不抵；100 是硬截断线，
75 覆盖"未截断但已噪"的区间。

## 2. 配置（`~/.config/otools/agrep.jsonc` 增加 `llm` 段）

段缺失 = 功能关闭，无任何 LLM 调用：

```jsonc
{
  "llm": {
    "style": "openai_compatible", // anthropic | openai | openai_compatible
    "base_url": "https://...",    // openai_compatible 必填
    "api_key": "...",
    "model": "...",
    "threshold": 75,              // 触发阈值，matches 条数
    "max_turns": 5,               // loop 最大轮数
    "timeout_ms": 90000           // 整体硬超时
  }
}
```

三种 style 覆盖全部目标：anthropic 走 Messages API；openai 走默认端点；
openai_compatible 经 `WithBaseURL` 覆盖 DeepSeek/Moonshot/Qwen/vLLM/网关。

## 3. 协助者 loop

输入：调用者的 `intent`、`pattern`、候选返回值（匹配块全文）、一组工具。

任务：理解调用者意图；可调用工具获取结构信息；判断是否需要改写返回值；
输出"保持原样"或替换文本。

工具集（小而硬，2~3 个，经 `codebase-memory-mcp cli` spawn 调用，与
`depSearchHint` 同机制，零新依赖）：

- `search_graph`：结构化代码搜索
- `trace_path`：调用链
- `get_code_snippet`：取符号源码

SDK：

- anthropic style：anthropic-sdk-go 的 beta `BetaToolRunner`（注册工具后
  自动跑 loop，pin 版本防 beta 漂移）
- openai / openai_compatible：openai-go 手写
  `for stop_reason == "tool_calls" { 执行 → append → 再调 }`，约 100 行

改写是删行的超集：协助者选择"删若干行"即过滤，选择"换成 dep_search 的
结构答案"即改写，选择"不动"即保持原样。

## 4. 输出契约与护栏

- 协助者只返回两种结果：`{"action": "none"}` 或
  `{"action": "filtered"|"rewritten", "content": "<替换后的匹配块>"}`。
  解析失败 / 超 `max_turns` / 超 `timeout_ms` → 按 `none` 处理，WARN 一行。
- 协助者产出不是 rg 的事实。发生实际改写时，Reminder 追加来源标记：

```text
[agrep_agent]: output rewritten by assistant agent; original stored under (session_id, message_id, turn_id).
```

- `max_turns` 与 `timeout_ms` 是硬顶：agrep 是高频工具，主 agent 阻塞等待，
  loop 失控的代价是分钟级。
- LLM 配置缺失、调用失败、额度耗尽 → 全部回退为原样输出，与记录同款的
  旁路降级语义。

## 5. 数据结构

新表（与 `agrep_records` 同库，三元组主键 join 到具体那次调用）：

```sql
CREATE TABLE IF NOT EXISTS agrep_llm_actions (
  session_id  VARCHAR(64)  NOT NULL,
  message_id  VARCHAR(64)  NOT NULL,
  turn_id     INT UNSIGNED NOT NULL,
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  action      VARCHAR(16)  NOT NULL,  -- none / filtered / rewritten
  before_text MEDIUMTEXT   NOT NULL,  -- 协助者介入前的匹配块
  after_text  MEDIUMTEXT   NOT NULL,  -- 最终采用的匹配块（none 时与 before 相同）
  PRIMARY KEY (session_id, message_id, turn_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

每次触发都落一行，`action=none` 也落：协助者的"不改写"判断本身是行为
数据。

## 6. 开放问题

- **全文型 intent 的风险**：intent 是"找字符串出现在哪 / audit 用法"时，
  rg 结果本身就是正确答案，改写只会引入错误。目前靠"允许不改写"让协助者
  自己兜底；是否在触发前加一层 intent 分类（结构性才触发），待定。
- **差模型的 tool calling 可靠性**：工具面已压到 2~3 个，schema 严格；
  实测若跑偏率高，再砍到只留 `search_graph`。
