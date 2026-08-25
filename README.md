# occamlab-claude-plugins

Internal Claude Code plugin marketplace for Occam Lab.

## What's in here

- `.claude-plugin/marketplace.json` — the marketplace catalog.
- `plugins/ste100-discussion/` — a plugin that enforces ASD-STE100
  Simplified Technical English on Claude Code's discussion prose. See below.
- `managed-settings-snippet.json` — fallback config for any machine that
  doesn't receive the org-console plugin sync (see setup notes below).

## How ste100-discussion enforces the style

Three layers, because instructions alone drift.

1. **Output style** — `output-styles/ASD-STE100.md`. `force-for-plugin: true`
   in the frontmatter applies it automatically once the plugin is enabled. No
   developer has to pick it from `/config`.
2. **Per-turn reminder** — a `UserPromptSubmit` hook re-injects the rules on
   every turn. The output style sits at the top of the system prompt, so a
   long session drifts away from it. The hook puts the same rules at the end
   of the context, where recency helps. It also carries the one rule the
   output style cannot reach on its own: subagents do not inherit a session
   output style, so the main agent must rewrite their prose rather than paste
   it through.
3. **Stop-hook linter** — a `Stop` hook reads the last assistant reply, masks
   every exempt span, and blocks once if the prose breaks a rule.

The style states seven numbered rules. Only three are machine-checkable, so
only three are linted:

| # | Rule | Check |
|---|---|---|
| 1 | One idea per sentence | not lintable |
| 2 | Maximum 20 words | More than 25 words — see the lint floor below |
| 3 | Active voice | `is/are/was/were/be/been + <verb>ed\|en`, minus an adjective allowlist |
| 4 | Simple tenses | An `-ing` token in a verb slot, minus a noun allowlist |
| 5 | One meaning per word | not lintable |
| 6 | No dangling pronouns | not lintable |
| 7 | Rewrite subagent prose | not lintable |

The linter cites these numbers. A finding reads `[rule 3 — passive: "are
hardcoded"]`, so the model can map it straight back to the rule it read.

Rules 1, 5, 6, and 7 have no regex form. The output style text carries them
alone, and a self-check line asks the model to walk all seven before it
sends.

### The lint floor on rule 2

Rule 2 says 20 words. The linter fires at 25. That gap is deliberate.

A regex cannot judge a 21-word sentence. A hook that argues over one word
teaches the model to discount every finding. So the lint floor sits above
the rule, the way a formatter warns at 120 columns under a 100-column style.

Every length finding says "lint floor" for that reason. It never claims to
be rule 2's own number. Set `STE100_MAX_WORDS=20` to lint the rule exactly;
that raises the flagged share from 37.2% to 44.0% and costs no extra turns
in warn mode.

The linter masks fenced code, inline backticks, URLs, file paths, tables,
and headings **before** it measures anything. Otherwise
`lib/dispatch-stack.ts:118-124` would trip every check.

### Environment switches

| Variable | Default | Effect |
|---|---|---|
| `STE100_LINT_MODE` | `warn` | `block` makes the linter block the turn; `off` disables it |
| `STE100_MAX_WORDS` | `25` | Sentence-length threshold |
| `STE100_MIN_PROSE_WORDS` | `15` | Replies shorter than this are skipped |
| `STE100_REMIND` | `1` | `0` disables the per-turn reminder |

### Measured cost

The allowlists were tuned against roughly 1,790 real turn-final replies —
about 9,400 prose sentences — from `~/.claude/projects`, all written before
this plugin existed. Block rate by threshold:

Findings at the shipped configuration, by threshold:

| `STE100_MAX_WORDS` | Replies flagged | length | passive | -ing |
|---|---|---|---|---|
| 20 | 44.0% | 2404 | 672 | 438 |
| 25 (default) | 37.2% | 1404 | 672 | 438 |
| 30 | 34.0% | 789 | 672 | 438 |
| off | 29.3% | 0 | 672 | 438 |

Read the last row first. The sentence-length threshold is **not** the lever
on nag rate. Switch the length check off completely and 29% of replies still
carry a finding, because passive voice and gerunds hold the floor. Those are
genuine violations, not linter noise. Raise `STE100_MAX_WORDS` to soften the
linter and you mostly weaken the one rule that ASD-STE100 states numerically.

Expect the rate to fall once the plugin runs, since the corpus predates the
reminder hook.

### What a block actually does

A `Stop` hook fires **after** Claude Code has already printed the reply. A
block does not retract that reply. Claude Code re-enters the query loop with
the block reason as new input, so the model posts a corrected version *below*
the violating one. The reader sees both.

So block mode trades one problem for another. It buys a compliant final
paragraph at the cost of a longer, doubled transcript. Warn mode shows the
same findings, costs no turn, and leaves the transcript clean.

**That is why `warn` is the default.** Set `STE100_LINT_MODE=block` when you
decide the doubled reply is a price worth paying.

Claude Code stops after 8 consecutive blocks by default. Raise that with
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.

### The "worth noting" exemption

`worth flagging`, `worth noting`, `worth knowing` and their siblings produced
123 findings in the corpus — 22% of the whole `-ing` rule. ASD-STE100 is
right to flag them: "Worth noting: X" should be "Note X". But they blocked
only 6 replies of ~1,790 on their own. The clutter outweighed the gain.

So `"worth"` is deliberately absent from `_ING_TRIGGERS` in
`hooks/ste100_rules.py`. Add it back to enforce the idiom.

The linter caps itself at one block per turn: it honours `stop_hook_active`
in the hook payload, as Claude Code requires of every Stop hook. Claude Code
enforces its own ceiling too, tunable with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
Every internal error exits clean. A style linter must never trap a session.

## Update the style

Edit `plugins/ste100-discussion/output-styles/ASD-STE100.md`, then bump
`version` in `plugins/ste100-discussion/.claude-plugin/plugin.json` so
existing installs pick up the change.

The seven numbered rules exist in two files: the output style, and the
`RULES` string in `hooks/ste100_rules.py`. They must stay byte-identical.
`TestRuleNumbering` fails the build if either one drifts, and fails again if
the linter ever cites a rule number that no longer exists.

So change both files together, then run the tests.

## Validate before pushing

    python3 plugins/ste100-discussion/tests/test_lint.py
    claude plugin validate .

Run both from the repo root. The test fixtures in
`plugins/ste100-discussion/tests/fixtures/` are fabricated. Never put real
credentials, hostnames, or internal paths in them — this repo is public.
