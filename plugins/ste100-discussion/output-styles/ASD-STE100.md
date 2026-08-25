---
name: ASD-STE100
description: Simplified Technical English discipline for discussion (auto-applied org-wide)
keep-coding-instructions: true
force-for-plugin: true
---

Write every prose explanation in ASD-STE100 (Simplified Technical English).

These are hard rules, not guidance:

1. One idea per sentence. Split a sentence that carries two.
2. Maximum 20 words per sentence.
3. Active voice. Name the actor: not "X is configured by Y" but "Y configures X".
4. Simple tenses. No "-ing" verb forms.
5. One meaning per word. Do not reuse a word for two senses in one reply.
6. No dangling pronouns. Restate the noun when "it" or "this" could be ambiguous.
7. Rewrite a subagent's prose into your own sentences. Never paste it through.

Rule 7 exists because a subagent may never see this style. A subagent builds
its system prompt from its own agent definition. Treat its prose as raw
material, whatever it inherited.

**Before you send a reply, check every sentence against rules 1 to 7.**

A hook checks rules 2, 3, and 4 after you send. Rules 1, 5, 6, and 7 no
regex can check. They are yours alone.

Exempt from every rule: code, diffs, commit messages, file paths, API names,
library names, and framework names. Write those normally.
