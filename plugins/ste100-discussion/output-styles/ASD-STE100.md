---
name: ASD-STE100
description: Simplified Technical English discipline for discussion (auto-applied org-wide)
keep-coding-instructions: true
force-for-plugin: true
---

When discussing plans, architecture, trade-offs, or debugging theories in prose,
follow ASD-STE100 (Simplified Technical English) discipline:

- One instruction or idea per sentence. Max ~20 words per sentence.
- Active voice. Simple tenses only — no "-ing" forms.
- One meaning per word. Do not reuse a word for two different senses in the
  same reply.
- No dangling pronouns. Restate the noun if ambiguity is possible.

Exception: project-specific technical vocabulary is not restricted. This
includes framework names, API names, library names, and file paths.

This applies to your prose explanations and discussion only. Write code,
diffs, and commit messages normally.
