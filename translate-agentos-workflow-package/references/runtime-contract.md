# AgentOS Workflow v3 可移植基线契约

本基线来自 2026-09-04 的 AgentOS 当前实现。它用于没有源码仓库时的候选包设计；目标 Runtime 的源码、`GET /api/agentos/v1/workflow-node-types` 或官方 admission 与本文件冲突时，以目标 Runtime 为准并报告漂移。

## 1. DSL、端口与图

- Authority 是 Package 内的 `workflow.yml`，`spec` 必须为 `agentos.workflow/v3`。
- 当前注册节点：`input@1`、`output@1`、`llm@1`、`tool@1`、`code@2`、`foreach@1`、`loop@1`、`poll@1`、`agent@1`、`human@1`、`workflow@1`。
- Workflow 必填 `id/version/entry/nodes/edges`，`subworkflows` 可省略。
- 节点声明 `type`、完整 `interface.inputs/outputs/routes`、严格 `config` 和可选 `policy`；未知字段 fail closed。
- 输入 source 只有两种：

```yaml
source: {kind: node, selector: [node_id, output_port, optional_field, 0]}
source: {kind: literal, value: 0.2}
```

- selector 前两段是节点 ID 和输出端口；edge 只表达执行/分支，数据依赖只由 selector 表达。
- required selector 来源必须支配消费者；条件分支来源绑定 optional 端口或拆成独立终点。
- 图必须是可达 DAG，entry 为 `input@1`，非终点有 outgoing edge。路由节点的 `interface.routes` 与条件边 `on` 完全一致。
- `policy.timeout_seconds` 为 1..86400，默认 300；`attempts` 为 1..10，默认 1。
- Skill 额外要求所有主图和子图 `input@1` outputs 使用 ASCII `snake_case`：`[a-z][a-z0-9_]*`。即使某目标 Runtime 容忍中文端口，也不得生成中文 Workflow 输入 key。

## 2. 端口 JSON Schema

使用受约束的 JSON Schema Draft 2020-12 子集：

- `type`、`properties`、`required`、`items`；
- `enum/const`；
- 数值范围与 `multipleOf`；
- 字符串长度与 `pattern`；
- 数组长度/唯一性、对象属性数量。

拒绝 `$ref`、`allOf/anyOf/oneOf/not`、`additionalProperties` 等白名单外关键字。Literal 必须匹配 Schema；selector 路径必须存在；来源 Schema 必须可静态证明可赋值给目标 Schema。

ArtifactRef 是普通 object 端口或 object 数组，不存在隐式 `files` side-channel 或累计 state bag。

## 3. 统一执行 Envelope

节点输入：

```python
{
    "meta": {
        "workflow_id": str,
        "workflow_version": str,
        "run_id": str,
        "node_id": str,
        "attempt": int,
    },
    "inputs": {"declared_port": value},
}
```

节点输出：

```python
{"outputs": {"declared_port": value}, "route": str | None}
```

Runtime 校验声明端口、必填值、Schema 和 route。不存在 `data/files`、隐式前驱透传、`preserve_input/include_input/result_key` 等旧协议。

## 4. 固定节点合同

### `input@1` / `output@1`

- `input@1.config: {}`，只有 outputs，用它声明图输入。
- `output@1` 可配 `message`；inputs 与 outputs 的名称、required 和 Schema 完全一致。

### `llm@1`

- Config：`prompt/includes/user_prompt/model/temperature/user_language/instruction/mode`。
- `mode: text` 恰好一个输出，原始字符串写入该端口。
- `mode: json` 根据 outputs 生成 strict JSON Schema，模型顶层对象键等于输出端口名。
- `images`、`videos` 是保留的 string-array 输入；`videos` 不支持 `mode: json`。
- 对业务强制合法 JSON 的场景，本 Skill 不直接依赖 `mode: json`：使用 `mode: text` 产出 `raw_json`，放入 `loop@1(max_iterations: 3)` 后由胶水代码解析和校验，确保失败可进入下一轮。

### `tool@1` / `poll@1`

- `tool@1.config` 只有 `name`；resolved inputs 直接形成工具 arguments。
- `poll@1` 对现有 task handle 调用注册工具，Config 包含 `name/handle_input/handle_argument/timeout_argument/timeout_seconds/max_polls/pending_path/pending_values/terminal_path/success_values/failure_values`。
- 异步外部能力使用 `tool@1` 提交，再用 `poll@1` 等待；不要在 `code@2` 中自己轮询。

### `agent@1`

- Config：`prompt/includes/resources/tools/skills/model/max_steps`。
- Agent 只能通过 `submit_output` 恰好一次提交与 outputs 匹配的对象。
- `skills` 是 Runtime Skill 名称允许列表。运行时从 `/skills` 加载这些 Skill；它们不属于 `.awpkg` 资源闭包，必须由目标 Run 的冻结 ResourceBinding 提供。
- 大型流程型 Skill 应拆成职责明确的小 Skill，再把所需名称写进对应 `agent@1.config.skills`。明确的一次调用改用 `llm@1`。

### `human@1` / `workflow@1`

- `human@1.config` 为 `message/fields/actions`；action id 与 routes 完全一致，恢复数据进入声明 outputs。
- `workflow@1.config` 为 `ref` 和可选 `lifecycle`；调用接口必须与子图 entry `input@1` 和唯一 `output@1` 完全匹配，禁止递归。
- `lifecycle` 可声明 `title/start_desc/done_desc/fail_desc/card_type`，用于执行卡片事件。

### `foreach@1`

- 对数组按稳定 item id 执行包内子工作流，支持显式依赖和有界并发。
- Config：`ref/items_input/shared_input/item_input/dependencies_input/item_id_path/depends_on_path/max_concurrency/failure_policy`。
- `max_concurrency` 为 1..32，`failure_policy` 当前仅 `all_required`；结果按原 item 顺序返回。

### `loop@1`

- 串行、1-based 地调用包内子工作流，承担唯一合法的有界状态反馈。
- Config：`ref/initial_state_input/shared_input/state_input/iteration_input/state_output/decision_output/continue_value/done_value/max_iterations`。
- `max_iterations` 为 1..100；child 必须输出不同的 state/decision 端口。decision 等于 `continue_value` 时继续，等于 `done_value` 时返回 state，其他值或耗尽均失败。
- AI JSON 合同固定使用 `max_iterations: 3`；第三次校验失败时 child 应返回业务失败 state + done，不能依靠 loop exhaustion 表达业务结果。

### `code@2`

- `config.path` 是 `resources/scripts/` 下规范化 UTF-8 `.py`；`resources` 声明额外包成员。
- 顶层恰好一个 `async def main(ctx, input)`；每次 attempt 在 fresh namespace 中执行。
- Runtime 的 `ctx` 技术上提供 run directory、资源、LLM、工具和事件能力，但本 Skill 对新包施加更严格的 authoring policy：`code@2` 只能做确定性胶水，不得调用 `ctx.llm/ctx.tool`，不得导入外部 SDK 或访问网络、数据库、对象存储、消息队列、子进程。
- 允许职责：stdlib 数据处理、JSON/业务校验、投影、组装、route/state 计算和本地 Run Artifact 文件操作。

## 5. AI JSON 三次校验合同

标准子工作流输入为 `state`、`iteration` 和可选 `shared`；输出为 `state`、`decision`。

1. 生成节点读取 state 中的原输入、上次错误和重试指令，输出字符串 `raw_json`。
2. 校验代码严格解析，拒绝重复键、非标准数值、错误顶层类型和业务字段错误。
3. 成功：state 写入 parsed result，decision=`done`。
4. 第 1/2 次失败：state 写入精确错误和完整重试指令，decision=`continue`。
5. 第 3 次失败：state 写入稳定失败合同，decision=`done`。

循环及 child 节点的 `policy.attempts` 都设为 1，保证总生成次数不超过 3。

## 6. Package 与冻结边界

`.awpkg` 是确定性 ZIP：

```text
workflow.yml
resources/references/<被引用 Prompt 或资源>
resources/scripts/<被引用 code@2 脚本>
```

- 闭包由 LLM/Agent `prompt/includes`、Agent `resources`、Code `path/resources` 推导。
- Package 成员必须精确等于 `workflow.yml + referenced_resources`；缺失与多余成员均失败。
- 小 Skill 不复制进 `.awpkg`；用独立 Skill 制品和冻结 ResourceBinding 解决依赖。
- 路径必须是规范 POSIX 相对路径；禁止穿越、重复、加密、目录成员和非普通文件。
- 上限：256 成员、总解压 64 MiB、单成员 32 MiB。
- Builder 固定成员顺序、时间戳、权限和压缩方式；相同输入生成相同字节与 SHA。
- 新 Run 冻结 Package 与 Skill 资源身份；checkpoint 恢复不得切换到 latest。

### WPM 身份与 Run 选择

- WPM 公开 key、metadata `key` 与包内 `workflow.id` 必须相同。WPM 的管理接口目前可以保存内部 id 不同的包，但 AgentOS 的 WPM Provider 在下载后会按 `(id, version, spec, size)` 核对 metadata，身份不一致会在 Run 启动前失败。
- WPM/AgentOS 远端版本必须是数字 SemVer `x.y.z`；每次发布创建新不可变版本，禁止覆盖同版本字节。
- `/internal/v1/workflow-packages/{key}/latest` 来源是 workflow 文档中的 `current_version_id`。不要按版本号大小、发布时间或上传顺序推断 current。
- AgentOS 新 Run 从 WPM current 解析一次，然后在 `ResourceBinding` 冻结 `workflow_key`、`workflow_version`、`workflow_package_sha256`、`workflow_spec`、`workflow_package_source`、`workflow_package_oss_key` 和 `workflow_package_size`。恢复已有 Run 必须复用这组身份，不得重新解析 latest。

## 7. 验证边界

便携 Builder 校验安全路径、大小、UTF-8、v3 spec、节点 Config、资源闭包、代码入口、输入 key、胶水代码限制和确定性 ZIP。它不能完整替代目标 Runtime 的 Pydantic Config、JSON Schema、拓扑、dominance、selector assignability、subworkflow 接口和真实执行验证。

- 便携预检 + 两次字节一致 + mock 回归 = 候选包。
- 目标 Runtime 文档校验 + Package admission + 定向测试 + 冻结恢复 = 认证黄金包。
- WPM 上传 + current/latest 回读 + 新 Run 冻结身份 + 精确 parent SSE 终态 + 最终业务输出 = 发布运行通过。
