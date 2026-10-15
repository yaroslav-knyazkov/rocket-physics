#!/usr/bin/env python
"""PreToolUse nudge: point the model at graphify before raw code reads / greps.

Usage: graphify_nudge.py read|bash
- read: Read of any source-code file (not .md/.txt/.json, not node_modules/.venv/graphify-out).
- bash: command contains grep/rg and is not already a graphify command.
Throttled: once per (session_id, agent_id | agent_type | "main", mode). Never fails: any error -> exit 0, no output.
"""
import json
import os
import re
import sys
import tempfile

CODE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".go", ".rs", ".java", ".rb",
            ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".kt", ".swift", ".php", ".scala", ".lua")
SKIP_PARTS = ("node_modules/", ".venv/", "venv/", "graphify-out/", "dist/", "build/", ".claude/")

MSG_READ = ("graphify-out/graph.json exists. Before reading source files run `graphify query \"<question>\"`, "
            "`graphify explain \"<concept>\"` or `graphify path \"<A>\" \"<B>\"`; read raw files after that, "
            "or to modify/debug specific lines. Applies to subagents too.")
MSG_BASH = ("graphify-out/graph.json exists. Run `graphify query \"<question>\"` before grepping raw files; "
            "grep only after graphify has oriented you, or to modify/debug specific lines.")


def wants_read(tool_input):
    p = str(tool_input.get("file_path") or "").replace("\\", "/").lower()
    if not p.endswith(CODE_EXT):
        return False
    if any(s in p for s in SKIP_PARTS):
        return False
    return True


def wants_bash(tool_input):
    cmd = str(tool_input.get("command") or "")
    if not re.search(r"(?<![\w-])(grep|rg)(?![\w-])", cmd):
        return False
    return "graphify" not in cmd


def throttled(data, mode):
    """True if already emitted for this key; otherwise create the marker and return False."""
    who = data.get("agent_id") or data.get("agent_type") or "main"
    key = "%s__%s__%s" % (data.get("session_id") or "nosession", who, mode)
    key = re.sub(r"[^\w.-]", "_", key)
    d = os.path.join(tempfile.gettempdir(), "claude-graphify-nudge")
    os.makedirs(d, exist_ok=True)
    marker = os.path.join(d, key)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return False
    except FileExistsError:
        return True


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("read", "bash"):
        return
    data = json.loads(sys.stdin.read())
    ti = data.get("tool_input") or {}
    ok = wants_read(ti) if mode == "read" else wants_bash(ti)
    if not ok:
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    if not os.path.isfile(os.path.join(root, "graphify-out", "graph.json")):
        return
    if throttled(data, mode):
        return
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": MSG_READ if mode == "read" else MSG_BASH}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
