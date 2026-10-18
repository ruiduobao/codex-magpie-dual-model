# codex-magpie-dual-model

[中文](#中文) · [English](#english)

---

## 中文

让 **Codex** 用强模型负责规划与验收，用 **DeepSeek**（经 Magpie 网关）负责写代码、跑测试。

这是一个 [Codex skill](https://github.com/openai/codex)：装进 `~/.codex/skills/` 后，Codex 会在你配置或排查多模型分工时自动使用它。

### 它解决什么

多模型分工本身不难配，难的是四个会让人卡很久的坑。这个 skill 和配套的 `doctor.py` 就是为了跨过它们：

| 坑 | 表现 |
|---|---|
| `magpie codex subagent on` 不是开关 | 写入字面值 `"on"`，派生时报 `Unknown model 'on'` |
| Magpie 启动时回写 `config.toml` | 手改的主模型被改回去 |
| 任务封条 | 报 `task was sealed`，DeepSeek 读不到任务 |
| 推理档位模型相关 | `medium` 对某些模型不存在 |
| 角色文件覆盖默认值 | 配置全对，子代理仍烧 `gpt-6-astra` |

### 安装

```bash
# 1. 克隆
git clone https://github.com/ruiduobao/codex-magpie-dual-model.git

# 2. 装成 Codex skill
mkdir -p ~/.codex/skills
cp -r codex-magpie-dual-model ~/.codex/skills/

# 3. 自检（只读，不改任何东西）
python ~/.codex/skills/codex-magpie-dual-model/scripts/doctor.py check
```

Windows PowerShell：

```powershell
git clone https://github.com/ruiduobao/codex-magpie-dual-model.git
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -Recurse -Force .\codex-magpie-dual-model "$HOME\.codex\skills\"
python "$HOME\.codex\skills\codex-magpie-dual-model\scripts\doctor.py" check
```

### 配置要点

```toml
# 主代理：规划与验收
model = "codex/gpt-6.1-sol"
model_reasoning_effort = "high"

[agents]
default_subagent_model = "tecent-free/deepseek-v4.1-flash"
default_subagent_reasoning_effort = "high"   # 该模型只有 low/high/max
max_concurrent_threads_per_session = 2

[features]
multi_agent_v2 = false                        # 必须关闭
```

外加两件事：

1. Magpie 偏好里 `codexAgentsV1` 必须为 `true`（设置页叫 “Codex subagents on any model”）。
2. 主模型用 `magpie codex <provider/model>` 设置，不要手改文件。

改完**必须新开会话**，旧会话仍走旧协议。

### 使用

```bash
python scripts/doctor.py check      # 诊断
python scripts/doctor.py fix        # 安全修复（先备份）
python scripts/doctor.py routing    # 看实际路由了什么
python scripts/doctor.py roles      # 角色文件是否偏离目标模型
python scripts/doctor.py pin-roles  # 把所有角色固定到同一模型
```

在 Codex 里直接说「配置 Codex + Magpie 双模型」也会触发这个 skill。

### 怎么确认真的生效

**不要问子代理“你是什么模型”**——它会按通用系统提示词回答自己是 Codex/GPT，这不构成任何证据。

看网关日志：

```bash
python scripts/doctor.py routing
```

同一个 session id 下应交替出现主模型与 `tecent-free/deepseek-v4.1-flash`。

### 文档

- [配置参考](references/config-reference.md) —— 每个字段的含义与由来
- [排障](references/troubleshooting.md) —— 报错原文对照表
- [升级后检查](references/after-upgrade.md) —— Codex 或 Magpie 更新后怎么办

### 适用范围

只负责路由与角色配置，不管理密钥、订阅或额度。

### 验证环境

Codex CLI 0.163.0 · Magpie 0.1.1285 · Windows 11。字段会随版本变化，升级后请重跑 `doctor.py check`。

---

## English

Give **Codex** a strong model to plan and review with, and **DeepSeek** (through the Magpie gateway) to write code and run tests.

This is a [Codex skill](https://github.com/openai/codex): drop it into `~/.codex/skills/` and Codex uses it whenever you configure or debug multi-model routing.

### What it solves

The routing itself is easy. Four traps are what cost people hours, and this skill plus `doctor.py` exist to get past them:

| Trap | Symptom |
|---|---|
| `magpie codex subagent on` is not a switch | Writes the literal `"on"`, spawns fail with `Unknown model 'on'` |
| Magpie rewrites `config.toml` at startup | Your hand-edited lead model reverts |
| Task sealing | `task was sealed`; DeepSeek cannot read the task |
| Reasoning levels are per-model | `medium` does not exist on some models |
| Role files beat the default | Config is right, subagents still bill `gpt-6-astra` |

### Install

```bash
git clone https://github.com/ruiduobao/codex-magpie-dual-model.git
mkdir -p ~/.codex/skills
cp -r codex-magpie-dual-model ~/.codex/skills/
python ~/.codex/skills/codex-magpie-dual-model/scripts/doctor.py check
```

PowerShell on Windows:

```powershell
git clone https://github.com/ruiduobao/codex-magpie-dual-model.git
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -Recurse -Force .\codex-magpie-dual-model "$HOME\.codex\skills\"
python "$HOME\.codex\skills\codex-magpie-dual-model\scripts\doctor.py" check
```

### Configuration

```toml
# Lead: plans and reviews.
model = "codex/gpt-6.1-sol"
model_reasoning_effort = "high"

[agents]
default_subagent_model = "tecent-free/deepseek-v4.1-flash"
default_subagent_reasoning_effort = "high"   # this model offers low/high/max only
max_concurrent_threads_per_session = 2

[features]
multi_agent_v2 = false                        # must stay off
```

Plus two things outside the file:

1. Magpie's `codexAgentsV1` preference must be `true` (Settings → "Codex subagents on any model").
2. Set the lead model with `magpie codex <provider/model>`, not by editing the file.

Any change requires a **new thread**; old sessions keep the old protocol.

### Use

```bash
python scripts/doctor.py check      # diagnose
python scripts/doctor.py fix        # apply safe fixes (backs up first)
python scripts/doctor.py routing    # show what actually got served
python scripts/doctor.py roles      # flag roles that drift from the intended model
python scripts/doctor.py pin-roles  # point every role at one model
```

Asking Codex to "set up Codex + Magpie dual-model routing" also triggers the skill.

### Verifying it actually works

**Do not ask the subagent what model it is.** It answers from a generic system prompt and will claim to be Codex/GPT regardless of routing. That proves nothing.

Read the gateway log instead:

```bash
python scripts/doctor.py routing
```

One session id should show the lead model alternating with `tecent-free/deepseek-v4.1-flash`.

### Docs

- [Configuration reference](references/config-reference.md) — every field and why it exists
- [Troubleshooting](references/troubleshooting.md) — error text to cause
- [After an upgrade](references/after-upgrade.md) — what to do when Codex or Magpie updates

### Scope

Routing and agent roles only. It does not manage keys, subscriptions, or quotas.

### Verified against

Codex CLI 0.163.0 · Magpie 0.1.1285 · Windows 11. Field names move; re-run `doctor.py check` after upgrades.

---

## License

MIT
