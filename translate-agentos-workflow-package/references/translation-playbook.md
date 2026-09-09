# 原始 Skill 到 Workflow v3 翻译手册

## A. 建立可追踪清单

为原始 Skill 的每一项行为记录：原位置、业务职责、输入/输出、Prompt、工具、副作用、Artifact、分支、重试、失败合同和验证用例。至少覆盖：

- 参数补全、开发期追问和运行期人工审批；
- 全部 AI 调用及其是“一次推理”还是“多步骤方法”；
- Skill 内可独立复用的阶段、说明文件和脚本；
- CLI/stdin/stdout、环境变量、工作目录和中间文件；
- 外部 SDK、HTTP、数据库、对象存储、消息队列、并发、轮询和付费动作；
- JSON 输出、Schema、解析、修复与最大尝试次数；
- timeout、retry、部分成功、降级和所有终点。

未进入清单的行为视为潜在回归。默认保持 Prompt 与业务合同，不借迁移顺带改产品逻辑。

## B. 分类 AI 阶段

对每个 AI 阶段做以下判断：

1. 输入明确、一次推理即可完成：使用 `llm@1`。
2. 需要读取多份规则、执行稳定的多步骤方法、在步骤间自主判断或调用多个工具：将方法拆成职责单一的小 Skill，并使用 `agent@1.config.skills` 绑定。
3. 大 Skill 包含多个可独立复用阶段：拆成多个小 Skill，由不同 Agent 节点或子工作流分别承载；不要把整份大 Skill 作为单一 Agent Prompt。
4. 只是确定性解析、校验、投影或组装：使用 `code@2`，不创建 Agent。

为每个小 Skill 记录：名称、职责、来源段落、输入假设、允许工具、输出要求、版本/发布位置和目标 ResourceBinding 可用性。小 Skill 放在交付目录的 `runtime-skills/`，不进入 `.awpkg`。

## C. 识别 Runtime 能力缺口

扫描原脚本的 imports 和调用：

- 模型调用 → `llm@1` 或 `agent@1`；
- 已注册同步工具 → `tool@1`；
- 异步提交/查询 → `tool@1` + `poll@1`；
- 数组 fan-out → `foreach@1`；
- 有界状态反馈 → `loop@1`；
- HTTP、数据库、OSS、消息队列、第三方 SDK 且没有已注册能力 → 记录 Runtime 能力缺口并停止对应实现。

不得为了完成 Package 而把缺失能力改写到 `code@2`。需要在 AgentOS 中先开发工具或专用节点，并单独验证注册、参数和失败合同。

## D. 画控制流和数据流

1. 把串行、fan-out/fan-in、审批、循环和终止路径画成图。
2. Edge 只表达执行/分支；另列每个输入端口的 node selector 或 literal。
3. 把稳定、可独立测试的阶段设计为 `workflow@1` 子工作流。
4. 为所有节点定义完整 `interface.inputs/outputs/routes` 和 Schema。
5. required 来源必须支配消费者；分支数据用 optional 端口或独立终点。
6. ArtifactRef 作为普通命名端口传递。
7. human action id 与 routed edges 显式对应，不从 Prompt 猜分支。
8. 主图和子图所有 `input@1` outputs 使用 ASCII `snake_case`。

完成候选图后进入 Checkpoint 1/2；用户确认前只做只读查证和设计草案。

## E. 为 AI JSON 输出设计三次循环

每个要求合法 JSON 的 AI 阶段都采用以下形态：

```text
main.prepare_state(code@2)
  -> main.json_guard(loop@1, max_iterations=3, policy.attempts=1)

subworkflow generate-and-validate:
  input(state, iteration[, shared])
  -> generate(llm@1 mode=text 或 agent@1，输出 raw_json:string)
  -> validate_json(code@2，输出 state + decision)
  -> output(state + decision)
```

设计 state 时至少包含：原始业务输入、`raw_json`、`validation_error`、`retry_instruction`、`status` 和成功后的 parsed result。所有 key 使用英文。

校验代码必须：

- 用标准库严格解析 JSON；
- 拒绝重复 key、NaN 和 Infinity；
- 校验顶层类型、必填字段、数组/对象形状和业务不变量；
- 第 1/2 次失败返回 `continue` 并携带精确错误；
- 第 3 次失败返回稳定失败 state + `done`；
- 成功返回 parsed result + `done`。

把所有循环相关节点 `policy.attempts` 设为 1。不要同时用平台 attempts 重试生成节点，否则会突破三次总上限。不要使用 `llm@1 mode: json` 作为这条业务重试链路的唯一保障，因为解析/Schema 失败会先终止节点。

## F. 实现 code@2 胶水

每个代码节点一份 Python 文件：

1. 保留短小纯函数，删除 argparse、stdout/result-file 协议和硬编码绝对路径。
2. 提供唯一入口 `async def main(ctx, input)`。
3. 只从 `input["inputs"]` 读取声明端口。
4. 返回 `{"outputs": {...}, "route": None}` 或声明 route。
5. 使用标准库完成确定性数据处理；必要时在 `ctx.run_dir` 幂等读写本地 Artifact。
6. 额外 Package 成员在 `config.resources` 声明并通过受控资源接口读取。
7. 不调用 `ctx.llm/ctx.tool`，不导入外部 SDK，不访问网络、数据库、OSS、消息队列或子进程。
8. 不实现 retry、poll、fan-out 或长流程；分别交给 `loop@1`、`poll@1`、`foreach@1` 和子工作流。
9. 不依赖跨 attempt/Run 的模块全局状态。

## G. 编写 workflow.yml

- 使用 `spec: agentos.workflow/v3`，每个节点写完整 interface 与严格 config。
- 主图和子图 input key 使用 `[a-z][a-z0-9_]*`。
- 输入数据只通过 selector/literal 绑定。
- Prompt 放 `resources/references/**`，胶水脚本放 `resources/scripts/**`；YAML 不内联 Python。
- `tool@1` inputs 就是工具 arguments；动态参数也由端口来源表达。
- 一次模型调用使用 `llm@1`；多步骤小 Skill 使用 `agent@1.config.skills`。
- `agent@1` 的 Skill 名称必须出现在 `skill-dependencies.md`，并验证 Runtime 可用性。
- 异步工具显式写成 submit tool → extract handle（必要时胶水）→ poll。
- AI JSON 生成使用三次 `loop@1` 结构。
- 每条可达终止路径使用明确 `output@1`。
- `workflow@1`、`foreach@1`、`loop@1` 与子图接口逐端口严格匹配。

## H. 形成严格资源闭包

在独立 `package-source/` 中确认：

- 每个 LLM/Agent prompt/includes 存在；
- 每个 Code path/resources 存在；
- 没有依赖未入包的 README、Schema 或本机绝对路径；
- 没有把 Runtime 小 Skill 错塞进 Package；
- 端口 Schema 已内联，无 `$ref` 或白名单外组合关键字；
- 没有未引用成员，不手工 zip。

## I. 测试矩阵

### Package/DSL

- build/load、身份、资源闭包、SHA、两次构建字节一致；
- 非 v3、未知节点、非法 Config、缺/多资源、路径穿越、错误 main 均拒绝；
- 中文/非法 input key、code 中第三方 import、`ctx.llm/ctx.tool` 均由便携预检拒绝；
- selector、dominance、Schema assignability、route 和子图接口由 Runtime admission 验证。

### JSON guard

- 第一次合法；第二次合法；第三次合法；三次均非法；
- 重复 key、NaN/Infinity、数组代替对象、缺字段、字段类型错误；
- 第三次失败返回业务失败结果且没有第四次模型调用；
- `policy.attempts=1`，实际生成调用次数不超过 3。

### 业务和外部能力

- 原阶段 mock 输出、Prompt/include 顺序、工具 arguments、轮询和审批路径；
- Agent 小 Skill 的允许列表、实际可见性和输出合同；
- 缺失工具/节点 fail closed，不回退到 code SDK；
- 不调用真实付费或不可逆工具，除非获得单独授权。

## J. 认证与交付

1. 构建候选包，记录 SHA、成员数和重复构建结果。
2. 有目标 Runtime 时执行文档校验、Package admission、定向测试和冻结恢复。
3. 核对小 Skill 与 Package 是否在同一目标 ResourceBinding 中可用。
4. 面向 WPM 时用 `--workflow-key <key>` 构建，强制公开 key 与包内 `workflow.id` 一致；版本使用新的数字 SemVer。
5. 获准上传后调用 WPM 本地包接口；上传会执行 AgentOS DSL 和完整包接纳并发布为新的不可变版本。回读 workflow 详情和 latest 元数据，核对 `current_version_id`、key、version、SHA256、size 与 ossKey，不能只相信上传响应。
6. 获准真实运行后创建新 thread/new Run；不得复用旧 Run 证明新包生效。读取原始 AG-UI SSE，只有精确 parent `runId` 的 `RUN_FINISHED`/`RUN_ERROR` 是父 Run 终态；同时检查最终 Workflow 输出，不以 accepted 或节点事件代替结果。
7. Package 不接纳、身份不一致、JSON 次数超限、能力缺口未补齐或 mock 语义漂移时停止发布/运行。
8. Checkpoint 3 只确认实现差异和尚未授权的外部动作。用户在当前任务中已明确授权的上传或 Run 不重复询问。
9. 无明确授权不提交、推送、上传、切 current、真实运行或部署；这些动作分别报告。

交付报告至少包括：

```text
结果：<已完成/阻塞>
Workflow：<id>@<version>，spec=<spec>
包：<绝对路径>，sha256=<hash>，members=<count>
验证等级：<设计完成/候选包/认证黄金包>
小 Skill：<名称、版本/来源、Runtime 可用性>
JSON guard：<max_iterations=3，实际测试调用次数>
能力缺口：<无/工具或节点列表>
验证：<命令与结果>
未验证：<真实模型/MCP/对象存储/部署>
外部动作：commit=<状态>，push=<状态>，publish=<状态>，deploy=<状态>
WPM：key=<key>，version=<version>，current_version_id=<id>，latest_sha256=<sha>
Run：thread=<id>，run=<id>，binding=<key/version/sha/source>，parent_terminal=<event>，output=<摘要>
```
