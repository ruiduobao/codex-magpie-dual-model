#!/usr/bin/env python3
"""Doctor for Codex + Magpie dual-model routing.

Modes:
    check    read-only diagnosis
    fix      apply safe fixes (backs up first)
    routing  summarize what Magpie actually served

Exit codes: 0 healthy, 1 problems found, 2 unreachable dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

IS_WIN = platform.system() == "Windows"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
MAGPIE_CONFIG = Path(
    os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
) / "magpie"

OK, WARN, FAIL = "ok", "warn", "fail"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, level: str, title: str, detail: str = "") -> None:
        self.rows.append((level, title, detail))

    def worst(self) -> str:
        levels = [r[0] for r in self.rows]
        if FAIL in levels:
            return FAIL
        if WARN in levels:
            return WARN
        return OK

    def render(self) -> None:
        marks = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
        for level, title, detail in self.rows:
            print(f"{marks[level]} {title}")
            if detail:
                for line in detail.splitlines():
                    print(f"       {line}")


# --------------------------------------------------------------------------
# discovery helpers
# --------------------------------------------------------------------------


def find_magpie() -> str | None:
    """Locate the magpie executable without requiring it on PATH."""
    for name in ("magpie", "magpie-windows-amd64", "magpie-windows-amd64.exe"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        Path("/Applications/Magpie.app/Contents/MacOS/magpie"),
        Path("/usr/local/bin/magpie"),
        Path("/usr/bin/magpie"),
        Path.home() / ".local/bin/magpie",
        Path(r"F:\Program Files\magpie-windows-amd64.exe"),
        Path(r"C:\Program Files\magpie-windows-amd64.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/magpie/magpie.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _origin(url: str) -> str:
    """Reduce a configured endpoint to scheme://host:port."""
    match = re.match(r"(https?://[^/]+)", url.strip())
    if not match:
        return url.rstrip("/")
    origin = match.group(1).rstrip("/")
    # A provider base_url is commonly ".../v1"; strip it so callers can append
    # "/v1/models" without producing "/v1/v1/models".
    return origin


def gateway_base() -> str:
    """Read the gateway base URL from Codex config, falling back to the default."""
    cfg = load_codex_config()
    providers = cfg.get("model_providers") or {}
    for key in ("magpie", "custom"):
        base = (providers.get(key) or {}).get("base_url")
        if base:
            return _origin(base)
    openai_base = cfg.get("openai_base_url")
    if openai_base:
        # "http://host:port/backend-api/codex" -> "http://host:port"
        return _origin(openai_base)
    return "http://127.0.0.1:3425"


def http_json(url: str, timeout: float = 8.0, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_codex_config() -> dict:
    path = CODEX_HOME / "config.toml"
    if not path.is_file():
        return {}
    if tomllib is None:
        return _parse_toml_flat(path.read_text(encoding="utf-8"))
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _parse_toml_flat(text: str) -> dict:
    """Minimal fallback parser: top-level scalars plus [agents]/[features]."""
    out: dict = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        header = re.match(r"^\[([^\]]+)\]$", line)
        if header:
            section = header.group(1)
            continue
        match = re.match(r"^([A-Za-z0-9_]+)\s*=\s*(.+)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value in ("true", "false"):
            value = value == "true"
        if section in ("", "agents", "features"):
            target = out if section == "" else out.setdefault(section, {})
            target[key] = value
    return out


def magpie_models(base: str) -> dict[str, dict]:
    """Return model id -> metadata from the gateway."""
    try:
        payload = http_json(f"{base}/v1/models")
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    return {m.get("id", ""): m for m in payload.get("data", [])}


def magpie_prefs() -> dict:
    path = MAGPIE_CONFIG / "settings.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def codex_models() -> dict[str, dict]:
    """Model catalog Codex itself sees, keyed by slug."""
    exe = shutil.which("codex")
    if not exe:
        return {}
    try:
        proc = subprocess.run(
            [exe, "debug", "models"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        payload = json.loads(proc.stdout)
    except (subprocess.SubprocessError, ValueError, OSError):
        return {}
    models = payload.get("models", payload if isinstance(payload, list) else [])
    return {m.get("slug", ""): m for m in models if isinstance(m, dict)}


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_gateway(rep: Report, base: str) -> bool:
    try:
        http_json(f"{base}/v1/models", timeout=6)
    except urllib.error.HTTPError as exc:
        rep.add(WARN, f"Gateway answered HTTP {exc.code} at {base}",
                "Reachable but rejecting /v1/models; check the gateway key.")
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        rep.add(FAIL, f"Magpie gateway unreachable at {base}",
                f"{exc}\nStart Magpie, then re-run this command.")
        return False
    rep.add(OK, f"Magpie gateway reachable at {base}")
    return True


def check_models(rep: Report, base: str, lead: str | None, worker: str | None) -> None:
    models = magpie_models(base)
    if not models:
        rep.add(WARN, "Could not list models; skipping model checks")
        return
    for label, model in (("lead", lead), ("subagent", worker)):
        if not model:
            rep.add(FAIL, f"No {label} model configured")
            continue
        if model not in models:
            near = [m for m in models if model.split("/")[-1].lower() in m.lower()][:4]
            hint = f"Close matches: {', '.join(near)}" if near else "Run `magpie models` for the current list."
            rep.add(FAIL, f"{label} model not served: {model}", hint)
            continue
        rep.add(OK, f"{label} model exists: {model}")


def check_effort(rep: Report, base: str, cfg: dict) -> None:
    models = magpie_models(base)
    if not models:
        return
    lead = cfg.get("model")
    agents = cfg.get("agents") or {}
    worker = agents.get("default_subagent_model")
    for label, model, effort in (
        ("lead", lead, cfg.get("model_reasoning_effort")),
        ("subagent", worker, agents.get("default_subagent_reasoning_effort")),
    ):
        if not model or not effort or model not in models:
            continue
        allowed = models[model].get("reasoning_levels") or [
            item.get("effort") for item in models[model].get("supported_reasoning_levels", [])
        ]
        allowed = [a for a in allowed if a]
        if not allowed:
            continue
        if effort not in allowed:
            rep.add(FAIL, f"{label} reasoning effort '{effort}' unsupported by {model}",
                    f"Supported: {', '.join(allowed)}")
        else:
            rep.add(OK, f"{label} reasoning effort valid: {model} -> {effort}")


def check_config(rep: Report, cfg: dict) -> None:
    lead = cfg.get("model")
    agents = cfg.get("agents") or {}
    worker = agents.get("default_subagent_model")
    effort = cfg.get("model_reasoning_effort")
    sub_effort = agents.get("default_subagent_reasoning_effort")
    features = cfg.get("features") or {}

    rep.add(OK if lead else FAIL, f"Lead model: {lead or 'unset'}")
    rep.add(OK if worker else WARN, f"Default subagent model: {worker or 'unset'}")
    if effort:
        rep.add(OK, f"Lead effort: {effort}")
    if sub_effort:
        rep.add(OK, f"Subagent effort: {sub_effort}")

    if worker == "on":
        rep.add(FAIL, "default_subagent_model is the literal string \"on\"",
                "`magpie codex subagent on` wrote this. It is not a switch.\n"
                "Set a real model id, and enable the codexAgentsV1 preference instead.")
    elif worker and "/" not in str(worker) and worker not in ("default", ""):
        rep.add(WARN, f"Subagent model lacks a provider prefix: {worker}",
                "Prefer provider/model so the gateway does not have to guess.")

    if features.get("multi_agent_v2"):
        rep.add(FAIL, "features.multi_agent_v2 is on",
                "Codex V2 re-seals subagent tasks and beats Magpie V1.\n"
                "Set it to false, then start a new thread.")
    else:
        rep.add(OK, "features.multi_agent_v2 is off")


def check_pref(rep: Report) -> None:
    prefs = magpie_prefs()
    if not prefs:
        rep.add(WARN, "Magpie settings.json not found",
                f"Expected at {MAGPIE_CONFIG / 'settings.json'}")
        return
    if prefs.get("codexAgentsV1"):
        rep.add(OK, "Magpie codexAgentsV1 is on (subagent tasks go as text)")
    else:
        rep.add(FAIL, "Magpie codexAgentsV1 is off",
                "Cross-model subagents will fail with a sealed-task error.\n"
                "Run `doctor.py fix`, then restart Magpie and open a new thread.")


def check_roles(rep: Report, cfg: dict) -> None:
    agents_dir = CODEX_HOME / "agents"
    if not agents_dir.is_dir():
        rep.add(WARN, "No agents directory", f"Expected {agents_dir} only if you use role files.")
        return
    roles = sorted(agents_dir.glob("*.toml"))
    if not roles:
        rep.add(OK, "No role files; default subagent model applies to every spawn")
        return
    for path in roles:
        text = path.read_text(encoding="utf-8", errors="replace")
        has_name = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.M)
        model = re.search(r'^\s*model\s*=\s*"([^"]+)"', text, re.M)
        effort = re.search(r'^\s*model_reasoning_effort\s*=\s*"([^"]+)"', text, re.M)
        name = has_name.group(1) if has_name else None
        if not name:
            rep.add(FAIL, f"{path.name}: missing `name`",
                    "Directory-discovered role files must declare name or they are silently ignored.")
            continue
        if name != path.stem:
            rep.add(WARN, f"{path.name}: name '{name}' differs from filename",
                    "Harmless, but the role is addressed by `name`, not by filename.")
        detail = f"model={model.group(1) if model else 'inherited'}"
        if effort:
            detail += f", effort={effort.group(1)}"
        rep.add(OK, f"Role '{name}' loaded ({path.name})", detail)


def check_usage(rep: Report) -> None:
    path = MAGPIE_CONFIG / "usage.jsonl"
    if not path.is_file():
        rep.add(WARN, "No usage log yet", f"Expected {path} after the first request.")
        return
    sessions: dict[str, set[str]] = {}
    tail: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                tail.append(line)
                if len(tail) > 400:
                    tail.pop(0)
    except OSError as exc:
        rep.add(WARN, "Could not read usage log", str(exc))
        return

    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        session = entry.get("session")
        served = entry.get("served") or entry.get("req")
        if session and served:
            sessions.setdefault(str(session), set()).add(str(served))

    mixed = [s for s, models in sessions.items() if len(models) > 1]
    if mixed:
        newest = mixed[-1]
        rep.add(OK, "Recent session used more than one model",
                f"session {newest[:13]}: {', '.join(sorted(sessions[newest]))}")
    elif sessions:
        rep.add(WARN, "Recent sessions show a single model",
                "No mixed-model session found yet. Spawn a subagent, then re-check.")
    else:
        rep.add(WARN, "Usage log has no parseable entries")


# --------------------------------------------------------------------------
# fixes
# --------------------------------------------------------------------------


def backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    import time

    dest = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, dest)
    return dest


def fix_pref(rep: Report) -> None:
    path = MAGPIE_CONFIG / "settings.json"
    if not path.is_file():
        rep.add(FAIL, "Cannot fix: Magpie settings.json not found",
                f"Expected {path}. Start Magpie once, then retry.")
        return
    try:
        prefs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.add(FAIL, "Cannot fix: settings.json is not valid JSON", str(exc))
        return
    if prefs.get("codexAgentsV1"):
        rep.add(OK, "codexAgentsV1 already on")
        return
    saved = backup(path)
    prefs["codexAgentsV1"] = True
    path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rep.add(OK, "Enabled codexAgentsV1",
            f"Backup: {saved}\nRestart Magpie, then start a new Codex thread.")


def fix_config(rep: Report, cfg: dict) -> None:
    path = CODEX_HOME / "config.toml"
    if not path.is_file():
        rep.add(FAIL, "Cannot fix: config.toml not found", f"Expected {path}")
        return
    text = path.read_text(encoding="utf-8")
    original = text

    if (cfg.get("features") or {}).get("multi_agent_v2"):
        text = re.sub(r"(?m)^(\s*multi_agent_v2\s*=\s*)true", r"\1false", text)
        if text == original:
            rep.add(WARN, "multi_agent_v2 is on but was not rewritten",
                    "Set features.multi_agent_v2 = false manually.")
        else:
            rep.add(OK, "Set features.multi_agent_v2 = false")

    if (cfg.get("agents") or {}).get("default_subagent_model") == "on":
        rep.add(FAIL, "default_subagent_model is \"on\" and needs a real model id",
                "This doctor will not guess your provider. Run:\n"
                "  magpie codex subagent_model <provider/model>")

    if text != original:
        saved = backup(path)
        path.write_text(text, encoding="utf-8")
        rep.add(OK, "Rewrote config.toml", f"Backup: {saved}")


def fix_roles(rep: Report) -> None:
    agents_dir = CODEX_HOME / "agents"
    if not agents_dir.is_dir():
        return
    for path in sorted(agents_dir.glob("*.toml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'^\s*name\s*=', text, re.M):
            continue
        saved = backup(path)
        patched = f'name = "{path.stem}"\n' + text
        path.write_text(patched, encoding="utf-8")
        rep.add(OK, f"Added missing `name` to {path.name}", f"Backup: {saved}")


# --------------------------------------------------------------------------
# routing summary
# --------------------------------------------------------------------------


def routing_summary(limit: int = 40) -> int:
    path = MAGPIE_CONFIG / "usage.jsonl"
    if not path.is_file():
        print(f"No usage log at {path}", file=sys.stderr)
        return 2
    entries = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    entries = entries[-limit:]
    if not entries:
        print("Usage log has no parseable entries", file=sys.stderr)
        return 2

    print(f"{'time':<10} {'requested':<40} {'served':<26} {'provider':<14} session")
    print("-" * 110)
    for entry in entries:
        stamp = str(entry.get("t", ""))[11:19]
        req = str(entry.get("req") or entry.get("model") or "-")
        served = str(entry.get("served") or "-")
        provider = str(entry.get("provider") or "-")
        session = str(entry.get("session") or "-")[:13]
        print(f"{stamp:<10} {req:<40} {served:<26} {provider:<14} {session}")

    by_session: dict[str, set[str]] = {}
    for entry in entries:
        if entry.get("session") and entry.get("served"):
            by_session.setdefault(str(entry["session"]), set()).add(str(entry["served"]))
    mixed = {s: m for s, m in by_session.items() if len(m) > 1}
    print()
    if mixed:
        newest = list(mixed)[-1]
        print(f"Mixed-model sessions found: {len(mixed)}. Newest: {newest[:13]}")
        print("  -> " + ", ".join(sorted(mixed[newest])))
        return 0
    print("No mixed-model session in this window. Spawn a subagent, then re-run.")
    return 1


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="check",
        choices=["check", "fix", "routing"],
        help="check (read-only), fix (apply safe fixes), routing (show served models)",
    )
    args = parser.parse_args()

    if args.mode == "routing":
        return routing_summary()

    base = gateway_base()
    cfg = load_codex_config()
    agents = cfg.get("agents") or {}
    lead = cfg.get("model")
    worker = agents.get("default_subagent_model")

    rep = Report()
    reachable = check_gateway(rep, base)
    check_config(rep, cfg)
    check_pref(rep)
    check_roles(rep, cfg)
    if reachable:
        check_models(rep, base, lead, worker)
        check_effort(rep, base, cfg)
    check_usage(rep)

    if args.mode == "fix":
        print("=== before ===")
        rep.render()
        print()
        print("=== applying fixes ===")
        fixes = Report()
        fix_pref(fixes)
        fix_config(fixes, cfg)
        fix_roles(fixes)
        fixes.render()
        print()
        print("Restart Magpie and start a new Codex thread for changes to take effect.")

    print()
    print("=== summary ===")
    rep.render()
    worst = rep.worst()
    print()
    print({"ok": "Healthy.", "warn": "Usable, but see warnings.",
           "fail": "Problems found."}[worst])
    return 0 if worst == OK else 1


if __name__ == "__main__":
    sys.exit(main())
