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
   it through. The reminder ends with a substitution table, because "use
   active voice" is harder to apply mid-sentence than `"are hardcoded in Y"
   -> "Y hardcodes"`.
3. **File check** — a `PostToolUse` hook on `Write|Edit`. It reads the prose
   the model just wrote, masks every exempt span, and blocks the turn if the
   prose breaks a rule.

Chat prose carries no check. Layers 1 and 2 govern it.

### Why the check moved off the Stop hook

An earlier version linted the last assistant reply on a `Stop` hook. That was
the wrong place, for two reasons.

A `Stop` hook fires **after** Claude Code has printed the reply. A block does
not retract it. Claude Code re-enters the query loop, so the model posts a
corrected version *below* the violating one. The reader sees both. So the
hook shipped in warn mode instead — and the warnings fired on **50.1%** of
prose replies while changing nothing. Nobody was measuring them.

`PostToolUse` has neither problem. Claude Code stops the agentic loop before
the next model call and shows the model the reason. The model rewrites the
file before a human reads it. Blocking there is free.

The trade is scope. The hook now sees written deliverables, not chat.

## The rules

The style states eight numbered rules. Only three are machine-checkable, so
only three are linted:

| # | Rule | Check |
|---|---|---|
| 1 | One idea per sentence | not lintable — see below |
| 2 | Maximum 20 words | More than 25 words — see the lint floor below |
| 3 | Active voice | `is/are/was/were/be/been + <verb>ed\|en`, minus an adjective allowlist |
| 4 | Simple tenses | An `-ing` token in a verb slot, minus a noun allowlist |
| 5 | One meaning per word | not lintable |
| 6 | No dangling pronouns | not lintable |
| 7 | Rewrite subagent prose | not lintable |
| 8 | No tool-call narration | not lintable |

The linter cites these numbers. A finding reads `[rule 3 — passive: "are
hardcoded"]`, so the model can map it straight back to the rule it read.

### Why rule 1 has no regex

Rule 1 is the top violation category, and the linter cannot see it. A
candidate detector looked for two coordinated finite verbs — the shape of
"reads the form body and pulls the phone number".

Measured over 1,404 real replies it hit 10.4% of them at roughly **30%
precision**. English reuses one shape for nouns and verbs, so the regex read
"both records are stale and the count is eleven" as two verbs. Standard
library Python has no part-of-speech tagger to break the tie.

A blocking check needs better than 30%, so the detector did not ship.

Many of its hits also sat inside narration sentences — "Let me check the
config and pull the logs". Rule 8 deletes those sentences outright, so it
removes much of rule 1's mass without any regex.

### Why rule 8 exists

**43.4%** of replies in the corpus opened with "Let me...", "I'll...", or
"I am going to...". That is the highest-density category measured, and the
lowest value to a reader. Deleting the sentence beats repairing it.

### The lint floor on rule 2

Rule 2 says 20 words. The linter fires at 25. That gap is deliberate.

A regex cannot judge a 21-word sentence. A hook that argues over one word
teaches the model to discount every finding. So the lint floor sits above
the rule, the way a formatter warns at 120 columns under a 100-column style.

Every length finding says "lint floor" for that reason. It never claims to
be rule 2's own number. Set `STE100_MAX_WORDS=20` to lint the rule exactly.

The linter masks fenced code, inline backticks, URLs, file paths, tables,
and headings **before** it measures anything. Otherwise
`lib/dispatch-stack.ts:118-124` would trip every check.

### Environment switches

| Variable | Default | Effect |
|---|---|---|
| `STE100_FILE_CHECK` | `on` | `off` disables the file check |
| `STE100_MAX_WORDS` | `25` | Sentence-length threshold |
| `STE100_MIN_PROSE_WORDS` | `15` | Bodies shorter than this are skipped |
| `STE100_REMIND` | `1` | `0` disables the per-turn reminder |
| `STE100_MAX_BLOCKS` | `3` | Blocks allowed on one file in one session |
| `STE100_GUARD_DIR` | system temp | Where the loop guard keeps its markers |

## Measured cost of the file check

Measured over 552 `Write` and `Edit` calls in `~/.claude/projects`, all
written before this plugin existed:

| Stage | Count | Share |
|---|---|---|
| `Write` / `Edit` calls | 552 | — |
| ...targeting a prose file | 228 | 41.3% |
| ...long enough to lint | 175 | — |
| ...flagged | 133 | 76.0% of lintable |

Findings per flagged body: median 4, p90 17.

Two numbers matter here.

**41.3%** says the hook is not dead code. The model writes Markdown often.

**76%** says the loop guard is load-bearing. Three of four prose bodies
break a rule today, so the hook needs a way to stop. It stops on a repeated
body, and after three blocks on one file.

### Scope of the check

The hook reads `file_path` and skips anything outside `.md`, `.markdown`,
`.mdx`, `.txt`, `.rst`, and `.adoc`. Code carries a blanket exemption from
every ASD-STE100 rule, and 59% of `Write`/`Edit` calls target code. Without
that filter the hook would be pure noise.

On `Edit` it judges `new_string` alone. `old_string` is prose from an
earlier turn, often from another author. Re-flagging it would block the
model over sentences it never wrote.

### The loop guard

`PostToolUse` has no `stop_hook_active` flag, and the rewrite is itself an
`Edit` that fires the hook again.

So the hook writes a marker under the system temp directory, keyed on the
session id and a hash of the file path. The marker holds one hash per body
the hook has already judged. Two conditions end the exchange:

- The model wrote a body the hook judged before. Nothing changed, so this is
  the true loop.
- The file reached `STE100_MAX_BLOCKS` blocks, three by default. This bounds
  a model that rewrites forever without converging.

The content key matters. A guard keyed on the path alone would block each
file once, and a still-dirty rewrite would ship in silence. At a 76% flag
rate and 4 findings per body, one nudge per file is not enforcement.

A marker it cannot read or write counts as absent. A broken guard must let
the check run, never silence it.

Every internal error exits clean. A style check must never trap a session.

### The "worth noting" exemption

`worth flagging`, `worth noting`, `worth knowing` and their siblings produced
123 findings in an earlier corpus pass — 22% of the whole `-ing` rule.
ASD-STE100 is right to flag them: "Worth noting: X" should be "Note X". But
they blocked only 6 replies of ~1,790 on their own. The clutter outweighed
the gain.

So `"worth"` is deliberately absent from `_ING_TRIGGERS` in
`hooks/ste100_rules.py`. Add it back to enforce the idiom.

## Update the style

Edit `plugins/ste100-discussion/output-styles/ASD-STE100.md`, then bump
`version` in `plugins/ste100-discussion/.claude-plugin/plugin.json` so
existing installs pick up the change.

The eight numbered rules exist in two files: the output style, and the
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
