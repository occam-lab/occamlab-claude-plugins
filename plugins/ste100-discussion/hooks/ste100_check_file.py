#!/usr/bin/env python3
"""PostToolUse hook: lint the prose the model writes to a file.

This hook replaced a Stop hook. The Stop hook fired after Claude Code
had already printed the reply, so a block appended a corrected reply
below the violating one. It never retracted anything. Its warn mode
fired on half of all replies and told the reader nothing.

A PostToolUse block costs nothing by comparison. Claude Code stops the
agentic loop before the next model call and shows Claude the reason.
The model rewrites the file before a human reads it.

Scope: prose files only. Code carries a blanket exemption from every
ASD-STE100 rule, and 59% of Write/Edit calls in a real corpus target
code. Without the extension filter this hook would be pure noise.

On Edit it judges `new_string` alone. `old_string` is prose from an
earlier turn, and often from another author.

Loop guard: PostToolUse has no `stop_hook_active` flag, and the rewrite
is itself an Edit that fires this hook again. Two conditions end the
exchange. The hook stops on a body it has already judged, which is the
true loop. It also stops after three blocks on one file, which bounds
a model that rewrites forever without converging.

A guard keyed on the file path alone would be simpler and much weaker.
Three of four prose bodies break a rule today, and a flagged body
carries 4 findings at the median. One block per file would nudge once
and then let the file ship dirty.

Any internal error exits 0. A style check must never trap a session.
"""

import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ASD-STE100 governs prose. These extensions carry prose.
PROSE_EXTENSIONS = {".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc"}

# How many times the hook may block one file in one session. The cap
# bounds a model that rewrites forever without ever converging.
MAX_BLOCKS_PER_FILE = int(os.environ.get("STE100_MAX_BLOCKS", "3"))


def _allow():
    sys.exit(0)


def _guard_dir(session_id):
    root = os.environ.get("STE100_GUARD_DIR") or os.path.join(
        tempfile.gettempdir(), "ste100-guard")
    return os.path.join(root, session_id or "no-session")


def _stop_here(session_id, file_path, body):
    """Return True when this hook must stay quiet about this file.

    The marker file holds one body hash per block already issued. The
    hook stops on a repeat hash, and stops once the file reaches
    MAX_BLOCKS_PER_FILE.

    A failure to read or write the marker returns False. A broken guard
    must let the check run, not silence it.
    """
    marker = os.path.join(_guard_dir(session_id),
                          hashlib.sha1(file_path.encode("utf-8")).hexdigest())
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
    try:
        seen = []
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as fh:
                seen = fh.read().split()
        if digest in seen:
            return True
        if len(seen) >= MAX_BLOCKS_PER_FILE:
            return True
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "a", encoding="utf-8") as fh:
            fh.write(digest + "\n")
    except Exception:
        return False
    return False


def main():
    if os.environ.get("STE100_FILE_CHECK", "on").lower() in ("0", "off", "false"):
        _allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()

    if payload.get("tool_name") not in ("Write", "Edit"):
        _allow()

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        _allow()

    file_path = tool_input.get("file_path") or ""
    if os.path.splitext(file_path)[1].lower() not in PROSE_EXTENSIONS:
        _allow()

    # Write carries the whole file. Edit carries only the new span.
    body = tool_input.get("content")
    if body is None:
        body = tool_input.get("new_string")
    if not body or not isinstance(body, str):
        _allow()

    from ste100_rules import lint, format_findings

    findings = lint(body)
    if not findings:
        _allow()

    if _stop_here(payload.get("session_id"), file_path, body):
        _allow()

    reason = "%s\n\n%s" % (os.path.basename(file_path),
                           format_findings(findings))
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _allow()
