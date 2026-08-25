#!/usr/bin/env python3
"""UserPromptSubmit hook: re-inject the ASD-STE100 rules every turn.

The output style sits at the top of the system prompt. In a long
session the model drifts away from it. This hook puts the same rules
at the end of the context on every turn, where recency helps.

It also carries the one rule the output style cannot reach: subagents
do not inherit a session output style, so the main agent must rewrite
their prose instead of pasting it through.

Exit 0 with text on stdout. Claude Code adds that text as context.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from ste100_rules import RULES
except Exception:
    # Never break the user's turn over a style reminder.
    sys.exit(0)

# Opt-out for a single session: STE100_REMIND=0
if os.environ.get("STE100_REMIND", "1") not in ("0", "false", "off"):
    sys.stdout.write(RULES + "\n")

sys.exit(0)
