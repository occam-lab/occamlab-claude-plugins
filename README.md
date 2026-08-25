# occamlab-claude-plugins

Internal Claude Code plugin marketplace for Occam Lab.

## What's in here

- `.claude-plugin/marketplace.json` — the marketplace catalog.
- `plugins/ste100-discussion/` — a plugin that ships one output style,
  `ASD-STE100`, applying Simplified Technical English discipline to Claude
  Code's discussion prose. `force-for-plugin: true` in the style's
  frontmatter makes it apply automatically once the plugin is enabled — no
  developer has to pick it from `/config`.
- `managed-settings-snippet.json` — fallback config for any machine that
  doesn't receive the org-console plugin sync (see setup notes below).

## Update the style

Edit `plugins/ste100-discussion/output-styles/ASD-STE100.md`, then bump
`version` in `plugins/ste100-discussion/.claude-plugin/plugin.json` so
existing installs pick up the change.

## Validate before pushing

    claude plugin validate .

Run from the repo root.
