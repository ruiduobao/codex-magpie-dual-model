---
name: codex-magpie-dual-model
description: Configure and repair Codex CLI/Codex app multi-model routing through the Magpie gateway, so a strong model (GPT-6.1 Sol or any Codex-plan model) plans and reviews while a cheaper model (DeepSeek via Magpie) writes code and runs tests as a native subagent. Diagnoses sealed-subagent failures, the Magpie config rewrite, unsupported reasoning levels, and agent role files that silently override the default subagent model with an expensive one. Use when setting up, migrating, re-validating after a Codex or Magpie upgrade, or troubleshooting "task was sealed" / "Unknown model" in Codex subagents, or when subagents bill the wrong model despite correct config. 配置与修复 Codex 经由 Magpie 网关的多模型分工：强模型负责规划与验收，DeepSeek 等廉价模型作为原生子代理执行编码与测试。可诊断子代理任务被封条加密、Magpie 回写配置、推理档位不支持，以及角色文件静默覆盖默认子代理模型导致误用昂贵模型等问题。适用于首次配置、Codex 或 Magpie 升级后重新校验，以及排查 "task was sealed"、"Unknown model" 或"配置正确但子代理仍走错模型"。
---

# Codex + Magpie Dual-Model Routing / Codex + Magpie 双模型分工

A GPT lead plans and reviews; a cheaper Magpie-served model implements. Both talk to the same Magpie gateway, so no per-agent `model_provider` override is needed — Codex roles can only override the model, never the provider.

让 GPT 主代理负责规划与审查，让 Magpie 提供的廉价模型负责实现。两者共用同一个 Magpie 网关，因此不需要给子代理单独覆盖 `model_provider`——Codex 的角色文件本来也只能覆盖模型，不能换 provider。

## Run the doctor first / 先跑自检

```bash
python scripts/doctor.py check      # diagnose only / 只诊断
python scripts/doctor.py fix        # apply safe fixes / 应用安全修复
python scripts/doctor.py routing    # what actually got served / 实际路由了什么
python scripts/doctor.py roles      # role files vs intended model / 角色文件与目标模型对比
python scripts/doctor.py pin-roles  # point every role at one model / 把所有角色固定到同一模型
```

`check` never writes. `fix` backs up before touching anything. Always print the doctor output before hand-editing config — most reported failures are one of the four traps below.

`check` 不写入任何东西，`fix` 改动前会备份。先看自检输出再手动改配置——绝大多数报错都出自下面四个坑。

## The four traps / 四个必踩的坑

These are the failures that cost real debugging time. Read them before changing config.

以下是真正耗时的失败点，改配置前务必先读。

### 1. `magpie codex subagent on` is not the right switch / 这条命令不是开关

It writes the literal string `"on"` into `[agents] default_subagent_model`, producing `Unknown model 'on'` for every spawn. The real control is Magpie's stored preference `codexAgentsV1` (Settings → "Codex subagents on any model"). Set it via `scripts/doctor.py fix`, or by adding `"codexAgentsV1": true` to `~/.config/magpie/settings.json` and restarting Magpie.

它会把字面值 `"on"` 写进 `[agents] default_subagent_model`，导致每次派生子代理都报 `Unknown model 'on'`。真正的开关是 Magpie 的偏好项 `codexAgentsV1`（设置页叫 “Codex subagents on any model”）。用 `scripts/doctor.py fix` 设置，或手工在 `~/.config/magpie/settings.json` 里加 `"codexAgentsV1": true` 后重启 Magpie。

### 2. Magpie rewrites `config.toml` on start / Magpie 启动时会回写配置

Hand-editing top-level `model` gets reverted at the next Magpie launch. Use `magpie codex <provider/model>` for the lead model and `magpie codex subagent_model <provider/model>` for subagents. Edit only what Magpie does not own.

手工改顶层 `model` 会在下次 Magpie 启动时被改回去。主模型用 `magpie codex <provider/model>`，子代理用 `magpie codex subagent_model <provider/model>`。只手工改 Magpie 不接管的部分。

### 3. Task sealing blocks cross-model subagents / 任务封条拦截跨模型子代理

Codex's ChatGPT-backed models seal the subagent task so only the same backend can open it; a Magpie-served DeepSeek cannot. Two conditions must both hold:

- `codexAgentsV1` is true, so Magpie hands tasks down as text.
- Codex's own `features.multi_agent_v2` is `false`; V2 wins over Magpie's V1 and re-seals.

Either change requires a **new thread**. An old session keeps the old protocol and will keep failing.

Codex 的 ChatGPT 模型会把子代理任务加密，只有同一后端能解开，Magpie 提供的 DeepSeek 解不开。必须同时满足两条：`codexAgentsV1` 为 true，让 Magpie 以文本下发任务；Codex 自己的 `features.multi_agent_v2` 为 `false`，因为 V2 会压过 Magpie 的 V1 并重新加密。任何一项改动都**必须新开会话**，旧会话仍走旧协议、仍然失败。

### 4. Reasoning levels are per-model, not universal / 推理档位随模型而变

Never assume `medium` exists. Read the model's `supported_reasoning_levels` from `magpie models` or `/v1/models` and pick from that list. As of this writing `tecent-free/deepseek-v4.1-flash` exposes only `low`, `high`, `max`.

不要假设 `medium` 一定可用。以 `magpie models` 或 `/v1/models` 返回的 `supported_reasoning_levels` 为准。撰写时 `tecent-free/deepseek-v4.1-flash` 只有 `low`、`high`、`max`。

### 5. Role files silently beat the default / 角色文件会压过默认设置

This is the one that looks like a total failure of the setup. A workspace configured correctly can still burn the most expensive model on every subagent, because `default_subagent_model` only applies when a spawn names no model **and** no role file overrides it. Role files carry their own `model`, and that wins.

这一条最容易被误判成整套配置失效。配置完全正确的环境，仍然可能在每个子代理上烧最贵的模型——因为 `default_subagent_model` 只在“派生时未指定模型**且**没有角色覆盖”时才生效。角色文件自带 `model`，优先级更高。

With `oh-my-codex` installed, `~/.codex/agents/*.toml` are generated from built-in definitions. In the version tested (oh-my-codex 0.21.8) every generated role hardcodes a model — `gpt-6-astra` for `explore`, `planner`, `architect`, `researcher`, and `gpt-6-luna` for the rest. The lead asks for `agent_type="explore"` or `"researcher"`, and the gateway serves `gpt-6-astra` even though the default subagent model says DeepSeek. Do not hardcode the role count; read it from the directory.

装了 `oh-my-codex` 时，`~/.codex/agents/*.toml` 由内置定义生成。在实测版本（oh-my-codex 0.21.8）里，每个生成的角色都写死了模型——`explore`、`planner`、`architect`、`researcher` 是 `gpt-6-astra`，其余是 `gpt-6-luna`。主代理一喊 `agent_type="explore"` 或 `"researcher"`，网关就发 `gpt-6-astra`，哪怕默认子代理模型写的是 DeepSeek。不要把角色数量写死，以目录实际内容为准。

Diagnose from the rollout, not from config. The `spawn_agent` call records the `agent_type`, and the gateway log records what answered:

从会话记录判断，不要只看配置。`spawn_agent` 调用里记着 `agent_type`，网关日志记着实际应答的模型：

```bash
python scripts/doctor.py roles        # role files vs. intended model
python scripts/doctor.py routing      # what actually answered
```

Fix through OMX's own config so a later `omx setup` does not undo it:

通过 OMX 自己的配置修复，避免下次 `omx setup` 覆盖掉：

```json
// ~/.codex/.omx-config.json
{
  "agentModels":   { "explore": "tecent-free/deepseek-v4.1-flash", "researcher": "tecent-free/deepseek-v4.1-flash" },
  "agentReasoning": { "explore": "high", "researcher": "high" }
}
```

`agentModels` is read with the highest priority in `resolveAgentModel`, above the hardcoded `exactModel`. Then re-run `omx setup` so the role files regenerate.

`agentModels` 在 `resolveAgentModel` 中优先级最高，压过硬编码的 `exactModel`。之后重跑 `omx setup` 让角色文件重新生成。

Listing every role by hand is error-prone. `pin-roles` enumerates the role files and writes the mapping for all of them, defaulting the model to your `[agents] default_subagent_model`:

逐个手写角色容易漏。`pin-roles` 会枚举角色文件并全部写入，模型默认取你的 `[agents] default_subagent_model`：

```bash
python scripts/doctor.py pin-roles                                   # every role -> default subagent model
python scripts/doctor.py pin-roles --model tecent-free/deepseek-v4.1-flash --effort high
omx setup                                                            # regenerate role files
python scripts/doctor.py roles                                       # confirm none drifted
```

If you do not use OMX, edit the `model` line in each role file directly — but expect any generator to overwrite it.

如果你不用 OMX，直接改各角色文件的 `model` 行也可以，但要预期生成器会覆盖。

## Reference layout / 参照配置

```toml
# Lead: planned and reviewed by a strong model.
model = "codex/gpt-6.1-sol"
model_reasoning_effort = "high"

[agents]
default_subagent_model = "tecent-free/deepseek-v4.1-flash"
default_subagent_reasoning_effort = "high"   # low | high | max only
max_concurrent_threads_per_session = 2

[features]
multi_agent_v2 = false                        # must stay off
```

A role file in `~/.codex/agents/<name>.toml` pins the model for one specialist. `name` is **required** in the file body — directory discovery passes no name hint, and omitting it silently drops the role.

`~/.codex/agents/<name>.toml` 可以为某个专职角色固定模型。文件里**必须**写 `name` 字段——目录发现路径不会提供名字提示，漏写会导致该角色被静默忽略。

```toml
name = "deepseek_worker"
description = "Implements code, edits files, runs tests, fixes errors."
model = "tecent-free/deepseek-v4.1-flash"
model_reasoning_effort = "high"
developer_instructions = """
You implement scoped tasks handed to you by the lead agent.
Read the relevant files before editing. Run the tests. Report files changed,
what changed, real command output, and anything unresolved.
Do not widen scope, delete data, or switch technical approach on your own.
"""
```

## Verify with evidence, not self-description / 用证据验收，别看模型自述

A subagent asked "what model are you" answers from the generic system prompt and will claim to be Codex/GPT. That proves nothing. Judge routing from the gateway log:

问子代理“你是什么模型”只会得到通用系统提示词的回答，会说自己是 Codex/GPT，这不能作为证据。要看网关日志：

```bash
python scripts/doctor.py routing
```

Or read `~/.config/magpie/usage.jsonl`: each request records `req`, `served`, and `provider`. A correct dual-model run alternates `codex/gpt-6.1-sol` (lead) with `tecent-free/deepseek-v4.1-flash` (subagent) inside one session id.

或直接读 `~/.config/magpie/usage.jsonl`，每条请求都记录 `req`、`served`、`provider`。正确的分工会在同一个 session id 内交替出现 `codex/gpt-6.1-sol`（主代理）与 `tecent-free/deepseek-v4.1-flash`（子代理）。

## Keeping it working after upgrades / 升级后如何保持可用

Codex and Magpie both move fast. After either updates, re-run `doctor.py check`. When it fails, work from the outside in: gateway reachable → model IDs exist → config values correct → subagent actually spawns → gateway log shows the intended split. Do not skip to editing config; a renamed model or a changed preference key is the more common cause.

Codex 与 Magpie 迭代都很快，任一升级后先跑 `doctor.py check`。失败时从外向内排查：网关可达 → 模型 ID 存在 → 配置值正确 → 子代理确实能起来 → 网关日志出现预期分工。不要一上来就改配置，模型改名或偏好键变更更常见。

See [references/config-reference.md](references/config-reference.md) for every field and the reasoning behind it, [references/troubleshooting.md](references/troubleshooting.md) for the full error-to-cause table, and [references/after-upgrade.md](references/after-upgrade.md) for a post-upgrade checklist.

字段含义见 [references/config-reference.md](references/config-reference.md)，完整报错对照表见 [references/troubleshooting.md](references/troubleshooting.md)，升级后检查清单见 [references/after-upgrade.md](references/after-upgrade.md)。

## Scope / 适用范围

This configures routing and agent roles. It does not manage API keys, subscriptions, or quotas, and it does not spend quota on its own beyond the test turns you ask for.

本技能只负责路由与角色配置，不管理密钥、订阅或额度，除你要求的测试轮次外不会自行消耗额度。
