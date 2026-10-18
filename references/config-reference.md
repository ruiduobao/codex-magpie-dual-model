# Configuration Reference / 配置参考

Everything here was verified against Codex CLI 0.163.0 and Magpie 0.1.1285. Field names change; re-verify with `doctor.py check` after upgrades.

以下内容基于 Codex CLI 0.163.0 与 Magpie 0.1.1285 实测。字段会变，升级后请用 `doctor.py check` 复核。

## How the pieces fit / 各组件关系

```
Codex lead (Sol)  ──req──▶  Magpie gateway  ──▶  Codex/ChatGPT backend  (plans, reviews)
        │                         │
        └──spawn_agent──▶  subagent task
                                  └──▶  provider backend  (DeepSeek writes, tests)
```

Codex sends everything to one base URL. Magpie picks the provider from the model id's prefix. Because both the lead and the subagent share that base URL, no `model_provider` override is needed — and Codex agent roles cannot override the provider anyway.

Codex 所有请求走同一个 base URL，Magpie 按模型 id 的前缀决定转发到哪个 provider。主代理与子代理共用这个地址，所以不需要覆盖 `model_provider`；而且 Codex 的角色文件本来也不支持覆盖 provider。

## Codex `config.toml` / Codex 配置

| Key | Meaning | Notes |
|---|---|---|
| `model` | Lead model id | Must include the provider prefix, e.g. `codex/gpt-6.1-sol` |
| `model_reasoning_effort` | Lead effort | Must be in that model's supported list |
| `[agents] default_subagent_model` | Fallback model for spawns that name none | Not a switch; never `"on"` |
| `[agents] default_subagent_reasoning_effort` | Fallback effort | Per-model list applies |
| `[agents] max_concurrent_threads_per_session` | Parallel subagents | Start at 1–2 |
| `[agents] max_depth` | Nesting depth | 2 is enough for lead → worker |
| `[features] multi_agent_v2` | Codex's own V2 protocol | **Must be false** for Magpie V1 routing |

### Provider block / provider 配置

```toml
[model_providers.magpie]
name = "magpie"
base_url = "http://127.0.0.1:3425/v1"
wire_api = "responses"
experimental_bearer_token = "magpie"
```

Two paths exist in practice:

- `openai_base_url = "http://127.0.0.1:3425/backend-api/codex"` — routes Codex's own subscription traffic through Magpie. This is what a Codex-plan model like `codex/gpt-6.1-sol` needs.
- `model_providers.magpie` with `wire_api = "responses"` — the generic OpenAI-compatible path.

在实践中存在两条路径：`openai_base_url` 指向 `/backend-api/codex`，用于让 Codex 订阅流量经过 Magpie，`codex/gpt-6.1-sol` 这类模型走这条；`model_providers.magpie` 配 `wire_api = "responses"` 则是通用 OpenAI 兼容路径。

Both work at once; keep whichever Magpie wrote and do not delete its auth fields.

两条可以并存。保留 Magpie 写入的那条，不要删除它写的认证字段。

## Agent role files / 角色文件

Path: `~/.codex/agents/<file>.toml`. Fields are the flattening of Codex's config schema plus three role-only keys.

路径为 `~/.codex/agents/<file>.toml`。字段是 Codex 配置 schema 的扁平写法，外加三个角色专属键。

| Key | Required | Meaning |
|---|---|---|
| `name` | **Yes** | Role name used by `agent_type`. Directory discovery passes no hint, so omitting it drops the role silently. |
| `description` | Recommended | Shown in spawn guidance |
| `nickname_candidates` | No | Display names for spawned agents; ASCII letters, digits, spaces, `-`, `_` |
| `model` | No | Pins this role's model, overriding the default subagent model |
| `model_reasoning_effort` | No | Pins effort |
| `developer_instructions` | Yes (required for directory-discovered roles) | Cannot be blank |

`name` 必填——目录发现不给名字提示，漏写会导致角色被静默丢弃。`developer_instructions` 对目录发现的角色也是必填且不能为空。

What a role **cannot** do: change `model_provider`, change sandbox or approval policy, or widen the parent's permissions. Roles only narrow or re-point the model.

角色**不能**做的事：改 `model_provider`、改沙箱或审批策略、扩大父级权限。角色只能收窄能力或换模型。

## Magpie preferences / Magpie 偏好

`~/.config/magpie/settings.json`

| Key | Meaning |
|---|---|
| `codexAgentsV1` | Boolean. Hands subagent tasks down as plain text so any provider can read them. Required for cross-model subagents. |
| `searcher` / `searcherEffort` | Web-search helper model |
| `vision` | Image-reading model |

`codexAgentsV1` 为布尔值，作用是让子代理任务以纯文本下发，任何 provider 都能读；跨模型子代理必须开启。

## Magpie CLI fields / Magpie 命令字段

```bash
magpie codex                                  # show current state
magpie codex <provider/model>                 # set the lead model
magpie codex effort high                      # set lead effort
magpie codex subagent_model <provider/model>  # pin every subagent
magpie codex subagent_effort high             # set subagent effort
magpie codex default                          # remove Magpie entirely
```

**Do not run `magpie codex subagent on`.** It writes the literal `"on"` into `default_subagent_model`. The preference above is the actual switch.

**不要执行 `magpie codex subagent on`**，它会把字面值 `"on"` 写进 `default_subagent_model`。真正的开关是上面的偏好项。

## Reading the gateway log / 读网关日志

`~/.config/magpie/usage.jsonl`, one JSON object per request.

每条请求一行 JSON。

| Field | Meaning |
|---|---|
| `req` | Model id the client asked for |
| `served` | Model that actually answered |
| `provider` | Backend that served it |
| `session` | Codex session id; a correct split shows both models under one id |
| `ep` | Endpoint path |

A healthy dual-model session:

一个正常的分工会话：

```
15:26:16  codex/gpt-6.1-sol                  gpt-6.1-sol          codex         01a14de6-b564
15:26:33  tecent-free/deepseek-v4.1-flash    deepseek-v4.1-flash  tecent-free   01a14de6-b564
15:26:42  codex/gpt-6.1-sol                  gpt-6.1-sol          codex         01a14de6-b564
```

## Why sealing exists / 封条为什么存在

Codex's ChatGPT backend can attach an encrypted task envelope that only that backend can open. It is a server-side integrity measure for subscription traffic, not something Magpie can decrypt. Magpie's V1 path avoids it by sending the task as text. V2 keeps the envelope, which is why `multi_agent_v2` must be off.

Codex 的 ChatGPT 后端会给任务附加只有它自己能解开的加密信封，这是服务端对订阅流量的完整性措施，Magpie 无法解密。Magpie 的 V1 路径改为以文本传递任务来绕开它；V2 仍保留信封，所以说 `multi_agent_v2` 必须关闭。
