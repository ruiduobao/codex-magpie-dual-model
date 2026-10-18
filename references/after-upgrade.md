# After a Codex or Magpie Upgrade / 升级后检查

Both tools change their internals often. Run this checklist instead of assuming the old config still applies.

两个工具内部迭代都很快。别假设旧配置仍然有效，按下面走一遍。

## 1. Snapshot the working state first / 先记录可用状态

Before upgrading, save what currently works so you can diff later.

升级前先保存当前可用的状态，方便之后对比。

```bash
python scripts/doctor.py check > doctor-before.txt
magpie codex > magpie-before.txt
cp ~/.codex/config.toml ~/.codex/config.toml.pre-upgrade
```

## 2. Re-run the doctor / 重新自检

```bash
python scripts/doctor.py check
```

| Symptom | Likely upgrade cause | Next step |
|---|---|---|
| Gateway unreachable | Port or launch method changed | Check `magpie ls` / the app is running |
| Model id not served | Model renamed or removed upstream | `magpie models`, pick the new id |
| Effort unsupported | Model now exposes a different level set | Read `supported_reasoning_levels` |
| `codexAgentsV1` off | Preference key renamed or migrated | Check Magpie Settings for the subagent toggle |
| `multi_agent_v2` on | Codex flipped a default | Set it back to `false` |
| Role missing from list | `name` field requirement changed | Inspect one role file |

## 3. Re-verify the actual split / 复核真实分工

A config that parses is not a config that routes. Spend one real turn on it.

配置能解析不等于能正确路由，花一轮真实请求验证。

```bash
codex exec --skip-git-repo-check "Spawn a subagent, ask it to reply CHILD_OK, and relay the answer."
python scripts/doctor.py routing | tail -5
```

Expect one session id with both a lead model and the worker model.

期望看到同一个 session id 下同时出现主模型与执行模型。

## 4. When the model catalog changed / 模型目录变化时

Codex validates spawn models against its catalog, which Magpie rewrites at startup. After a Magpie upgrade the catalog may list different slugs.

Codex 用模型目录校验派生模型，而该目录由 Magpie 在启动时重写。Magpie 升级后目录里的 slug 可能变化。

```bash
codex debug models | grep -i deepseek      # what Codex can spawn
magpie models | grep -i deepseek           # what the gateway serves
```

Slugs in the second list but not the first cannot be spawned. Restart Magpie (so it rewrites the catalog), then restart Codex.

只在第二条列表里出现的 slug 无法用于派生。重启 Magpie（让它重写目录）后再重启 Codex。

## 5. What usually breaks first / 通常最先坏的部分

In observed order, from most to least likely:

按实际观察到的频率，从高到低：

1. **Model ids.** Providers rename and retire models; the prefix (`codex/`, `tecent-free/`, `opencode-go/`) may also change.
2. **Magpie preference keys.** `codexAgentsV1` is a Magpie-internal name, not a documented Codex setting; it can be renamed or migrated.
3. **Codex `[agents]` schema.** Field names and role-file requirements evolve with multi-agent work.
4. **Codex feature defaults.** A previously-off feature such as `multi_agent_v2` can start defaulting to on.
5. **Sealing behavior.** The V1 text path is a compatibility route; upstream changes may alter or remove it.

1. **模型 id** —— provider 会改名、下线模型，前缀（`codex/`、`tecent-free/`、`opencode-go/`）也可能变。
2. **Magpie 偏好键** —— `codexAgentsV1` 是 Magpie 内部命名，不是 Codex 的公开设置，可能被改名或迁移。
3. **Codex 的 `[agents]` schema** —— 字段名与角色文件要求随多代理功能演进。
4. **Codex 功能默认值** —— 原本关闭的功能（如 `multi_agent_v2`）可能改为默认开启。
5. **封条机制** —— V1 文本通道是兼容路径，上游可能调整或移除。

## 6. If the text path is gone / 如果文本通道被移除

If a future version removes the V1 route entirely, the fallback is a same-backend split: run the lead and subagents both on Magpie-served models (for example a strong Magpie-routed model plus DeepSeek), so no ChatGPT-sealed task ever crosses backends. It costs more than the subscription path but keeps the planning/execution split intact.

若将来版本彻底移除 V1 通道，退路是同后端分工：主代理与子代理都用 Magpie 提供的模型（例如一个强模型加 DeepSeek），这样不会有 ChatGPT 加密任务跨后端传递。成本高于订阅路径，但保留了规划与执行的分离。

## 7. Report the breakage upstream / 向上游反馈

The two projects responsible are worth reporting to, since this pattern depends on a compatibility route:

这个方案依赖一条兼容路径，值得向这两个项目反馈：

- Codex: `https://github.com/openai/codex` — agent role schema, `[agents]` fields, sealing behavior.
- Magpie: `https://github.com/yetone/magpie` — `codexAgentsV1`, subagent model pinning, catalog rewriting.

Include the exact error text, both tool versions, and the `doctor.py check` output. The precise message is what makes these reports actionable.

附上完整报错原文、两个工具的版本，以及 `doctor.py check` 的输出。精确的报错信息才能让反馈可处理。
