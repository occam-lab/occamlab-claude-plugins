#!/usr/bin/env python3
"""Stop hook: lint the last assistant reply against ASD-STE100.

Reads the hook payload on stdin. Finds the last main-thread assistant
text message in the transcript. Masks every exempt span. Applies the
three machine-checkable rules. Blocks once so the model rewrites.

Modes, via STE100_LINT_MODE:

  warn  (default) -- print the findings, never block
  block           -- emit decision "block" with the findings
  off             -- do nothing

Warn is the default on purpose. A Stop hook fires after Claude Code has
already printed the reply. A block does not retract that reply. Claude
Code re-enters the query loop, so the model posts a corrected version
below the violating one. Block mode appends; it does not rewrite.

Loop guard: when the payload sets stop_hook_active, this hook exits
clean. That caps the linter at one block per turn.

Any internal error exits 0. A style linter must never trap a session.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _allow():
    sys.exit(0)


def main():
    mode = os.environ.get("STE100_LINT_MODE", "warn").lower()
    if mode == "off":
        _allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()

    # Loop guard. Without it the block would fire again on the rewrite.
    if payload.get("stop_hook_active"):
        _allow()

    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        _allow()

    text = _last_assistant_text(transcript_path)
    if not text:
        _allow()

    from ste100_rules import lint, format_findings

    findings = lint(text)
    if not findings:
        _allow()

    message = format_findings(findings)

    if mode == "warn":
        json.dump({"systemMessage": "ASD-STE100 warnings:\n" + message},
                  sys.stdout)
        sys.exit(0)

    json.dump({"decision": "block", "reason": message}, sys.stdout)
    sys.exit(0)


def _last_assistant_text(transcript_path):
    """Return the text of the last main-thread assistant message."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return None

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if entry.get("type") != "assistant":
            continue
        # Subagent turns run on a sidechain. Their style is not ours to judge.
        if entry.get("isSidechain"):
            continue

        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue

        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(p for p in parts if p).strip()
        if text:
            return text
        # An assistant turn of pure tool calls is not the final reply.
        # Keep looking backwards.

    return None


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        _allow()
