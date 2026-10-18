# Troubleshooting / 排障

Match the exact error text first; these messages are specific enough to identify the cause.

先按报错原文匹配，这些信息足够定位原因。

## Error → cause → fix / 报错对照表

### A model you never configured shows up in the usage log

**Cause:** Check the `kind` field before assuming a misroute. `memory_consolidation`, `thread_title`, `guardian`, and compaction are Codex's own background jobs. They use their own model and appear as a bare model name with no provider prefix. Only `collab_spawn` is a subagent. A `thread_title` request in particular lands at the same second as your test spawns, so it reads as a subagent in a UI that lists requests by time.

**原因：** 先看 `kind` 字段再判断是否走错。`memory_consolidation`、`thread_title`、`guardian`、压缩任务是 Codex 自己的后台作业，用自己的模型，日志里是不带 provider 前缀的裸模型名。只有 `collab_spawn` 才是子代理。尤其是 `thread_title`，它常常和你测试派生的时刻出现在同一秒，在按时间列请求的面板里就跟子代理一样。

```bash
python scripts/doctor.py routing   # splits collab_spawn from background kinds
```

**Fix:** point them at the cheap model too.

**修复：** 把它们也指向廉价模型。

```bash
magpie codex memories tecent-free/deepseek-v4.1-flash
```

Writes `[memories] extract_model` and `consolidation_model`.

写入 `[memories] extract_model` 与 `consolidation_model`。

### Config is correct but an existing thread still spawns the old model

**Cause:** Sessions read role files and the model catalog at startup. A thread opened before your change keeps the old definitions, and if it predates the `codexAgentsV1` flip it can also keep hitting the seal.

**原因：** 会话在启动时读取角色文件与模型目录。在你改动前开启的会话沿用旧定义；若它还早于 `codexAgentsV1` 的变更，还会继续撞封条。

**Diagnose:** look at `collab_spawn` entries for that session id — all carrying the old model is conclusive.

**诊断：** 看该 session id 的 `collab_spawn` 记录，全是旧模型即可确定。

**Fix:** start a new thread. There is no in-place migration, and debugging config against an old session wastes time.

**修复：** 新开会话。没有原地迁移，拿旧会话调配置只会浪费时间。

### Lead model became a word like `"title"`

**Cause:** `magpie codex <anything>` treats an unrecognized word as a model id. `magpie codex title` has no matching field, so Magpie writes `model = "title"` and the lead breaks.

**原因：** `magpie codex <任意词>` 会把无法识别的词当成模型 id。`magpie codex title` 没有对应字段，于是 Magpie 写入 `model = "title"`，主模型就坏了。

**Fix:** `magpie codex` prints the real field list — `model, effort, subagent, subagent_model, subagent_effort, memories, login`. Set the lead back:

**修复：** `magpie codex` 会打印真实字段表。把主模型改回来：

```bash
magpie codex codex/gpt-6.1-sol
python scripts/doctor.py check    # confirms the lead model resolves
```

### A subagent bills an expensive model despite correct config

**Cause:** A role file carries its own `model`, and a role's model beats `[agents] default_subagent_model`. With `oh-my-codex`, every generated role hardcodes a model — `gpt-6-astra` for `explore` / `planner` / `architect` / `researcher`, `gpt-6-luna` for the rest. The lead spawning `agent_type="explore"` gets astra, not the default. Check the count in `~/.codex/agents` rather than trusting a fixed number.

**原因：** 角色文件自带 `model`，其优先级高于 `[agents] default_subagent_model`。装了 `oh-my-codex` 时，每个生成的角色都写死了模型——`explore` / `planner` / `architect` / `researcher` 是 `gpt-6-astra`，其余是 `gpt-6-luna`。主代理派生 `agent_type="explore"` 拿到的是 astra，不是默认模型。角色数量以 `~/.codex/agents` 实际内容为准，不要相信固定数字。

**Diagnose:** confirm which role was requested, then which model answered.

**诊断：** 先确认请求的是哪个角色，再看实际应答的模型。

```bash
python scripts/doctor.py roles      # flags every drifted role
python scripts/doctor.py routing    # shows req vs. served
```

The rollout file records the `agent_type` passed to `spawn_agent`; the gateway log records what served it. Neither the config file nor the subagent's self-description is evidence.

会话记录里有传给 `spawn_agent` 的 `agent_type`，网关日志里有实际服务的模型。配置文件与子代理自述都不能作为证据。

Note the trigger: a run can be correct before the change and wrong after only because it is an **old thread**. Existing sessions keep their original protocol and role set; only a new thread picks up the new config. If a fresh session still bills the wrong model, the cause is the role files, not the session age.

注意触发条件：改动前后表现不同，可能只是因为那是**旧会话**。已有会话沿用启动时的协议与角色集，只有新会话才读取新配置。若新会话仍然走错模型，原因就在角色文件，与会话新旧无关。

**Fix:** pin all roles while keeping each role's prompt.

**修复：** 固定全部角色，同时保留各自提示词。

```bash
python scripts/doctor.py pin-roles --model tecent-free/deepseek-v4.1-flash --effort high
omx setup     # regenerate generated role files
python scripts/doctor.py roles       # confirm no role drifted
```

`pin-roles` writes `agentModels` / `agentReasoning` into `~/.codex/.omx-config.json`, which `resolveAgentModel` reads before the hardcoded `exactModel`. A later `omx setup` keeps the pin.

`pin-roles` 会写入 `~/.codex/.omx-config.json` 的 `agentModels` 与 `agentReasoning`，`resolveAgentModel` 在读硬编码 `exactModel` 之前先读它；之后再跑 `omx setup` 也不会丢。

Without OMX, edit each role's `model` line instead, expecting any generator to overwrite it.

不用 OMX 的话，直接改各角色的 `model` 行，但要预期生成器会覆盖。

### `Unknown model 'on' for spawn_agent. Available models: ...`

**Cause:** `magpie codex subagent on` wrote the literal string `"on"` into `[agents] default_subagent_model`. It is a malformed CLI invocation, not a switch.

**原因：** `magpie codex subagent on` 把字面值 `"on"` 写进了 `[agents] default_subagent_model`，这是命令用错，不是开关。

**Fix:**

```bash
magpie codex subagent_model tecent-free/deepseek-v4.1-flash
```

Then confirm with `doctor.py check` that `default_subagent_model` holds a real model id.

之后用 `doctor.py check` 确认该字段是真实模型 id。

### `This subagent's task was sealed by the server that answered its lead (codex), and only that server can open it; <model> can't.`

**Cause:** Magpie's V1 text path is not active. Either `codexAgentsV1` is off, or Codex's `features.multi_agent_v2` is on and wins.

**原因：** Magpie 的 V1 文本通道没有生效——要么 `codexAgentsV1` 关闭，要么 Codex 的 `features.multi_agent_v2` 开启并压过了 V1。

**Fix:** run `doctor.py fix`, restart Magpie, then **start a brand-new Codex thread**. `fork_turns="none"` does not help; the seal is on the task itself, not on the inherited history.

**修复：** 执行 `doctor.py fix`，重启 Magpie，然后**新开一个 Codex 会话**。`fork_turns="none"` 无效，因为封条在任务本身上，不在继承的历史里。

### `... but this thread runs Codex's multi-agent V2, whose tasks are sealed: it began before the setting was turned on, or Codex's own features.multi_agent_v2 is on in its config.`

**Cause:** The preference is now on, but this session started under the old protocol, or `multi_agent_v2` is still true.

**原因：** 偏好已开，但当前会话是在旧协议下启动的，或 `multi_agent_v2` 仍是 true。

**Fix:** set `features.multi_agent_v2 = false`, then start a new thread. Old threads never migrate.

**修复：** 设 `features.multi_agent_v2 = false`，再新开会话。旧会话不会迁移。

### `Model provider '...' not found` on resume

**Cause:** Resuming a thread whose stored `model_provider` was renamed or deleted.

**原因：** 恢复会话时，其记录的 `model_provider` 已被改名或删除。

**Fix:** restore the provider block in `config.toml`, or start a fresh thread.

**修复：** 在 `config.toml` 恢复该 provider 配置，或直接新开会话。

### A configured model silently does nothing

**Cause:** Codex's model catalog drives spawn-time validation. A model that exists at the gateway but not in Codex's catalog is rejected before any request is sent.

**原因：** Codex 用模型目录做派生时校验。网关有、但 Codex 目录里没有的模型，会在发出请求前就被拒绝。

**Fix:** `codex debug models` and confirm the slug is present. Magpie rewrites Codex's catalog at startup; restart Magpie, then restart Codex.

**修复：** 用 `codex debug models` 确认 slug 存在。Magpie 在启动时重写 Codex 的目录；重启 Magpie 后再重启 Codex。

### `magpie: command not found`

**Cause:** Magpie's CLI is not on `PATH`. On Windows the binary is typically `magpie-windows-amd64.exe` in `F:\Program Files\` or `C:\Program Files\`.

**原因：** Magpie 命令行不在 `PATH` 里。Windows 上通常是安装目录下的 `magpie-windows-amd64.exe`。

**Fix:** call it by full path, or add its directory to `PATH`. `doctor.py` locates it without `PATH`.

**修复：** 用完整路径调用，或把目录加入 `PATH`。`doctor.py` 可以不依赖 `PATH` 找到它。

### Changes to `model` in `config.toml` keep reverting

**Cause:** Magpie owns that key and rewrites it at startup.

**原因：** 这个键由 Magpie 接管，启动时会重写。

**Fix:** use `magpie codex <provider/model>` instead of editing the file.

**修复：** 用 `magpie codex <provider/model>` 设置，不要手改文件。

### Subagent runs, but on the lead's model

**Cause:** The spawn named no model and the role file or default is not what you think, or Magpie's `subagent_model` pins something else.

**原因：** 派生时没指定模型，而角色文件或默认值与你以为的不同；或 Magpie 的 `subagent_model` 固定了别的模型。

**Fix:** `magpie codex` prints the effective state; compare it with the role file. Remember Magpie's `subagent_model` pin overrides what the lead asks for.

**修复：** `magpie codex` 会打印当前生效状态，与角色文件对比。注意 Magpie 的 `subagent_model` 会覆盖主代理的指定。

### `failed to connect to websocket: HTTP error: 426 Upgrade Required`

**Cause:** Codex tries a websocket transport the gateway does not serve, then falls back. Harmless if the turn completes.

**原因：** Codex 尝试网关不提供的 websocket 传输后回退。只要回合正常完成就无影响。

**Fix:** none needed. Add `supports_websockets = false` to the provider block to quiet it.

**修复：** 无需处理。想消除日志噪音可在 provider 配置加 `supports_websockets = false`。

### `Exceeded skills context budget`

**Cause:** Too many installed skills; Codex drops descriptions to fit.

**原因：** 安装的 skill 过多，Codex 为放入上下文而丢弃描述。

**Fix:** unrelated to routing. Disable unused skills if it bothers you.

**修复：** 与路由无关。介意的话禁用不用的 skill。

## Fast triage / 快速分诊

Work outside-in. Stopping at the first failing layer avoids chasing downstream symptoms.

从外向内排查，遇到第一层失败就停下，避免追着下游症状跑。

```bash
# 1. Is the gateway up?
python scripts/doctor.py check | head -3

# 2. Are both model ids real right now?
python scripts/doctor.py check | grep -i "model exists"

# 3. Is the config what you think?
magpie codex

# 4. Did the last spawn actually change models?
python scripts/doctor.py routing | tail -5
```

## What does not work as evidence / 不能作为证据的东西

- **Asking the subagent what model it is.** It answers from a generic system prompt and will claim to be Codex/GPT regardless of routing.
- **A subagent reporting success.** It proves the task ran, not which model ran it.
- **Only checking `config.toml`.** Magpie rewrites it; the file can disagree with the running gateway.

- **问子代理自己是什么模型**——它按通用系统提示词回答，无论路由如何都会说自己是 Codex/GPT。
- **子代理报告成功**——只能证明任务跑过，不能证明是哪个模型跑的。
- **只看 `config.toml`**——Magpie 会重写它，文件内容可能与运行中的网关不一致。
