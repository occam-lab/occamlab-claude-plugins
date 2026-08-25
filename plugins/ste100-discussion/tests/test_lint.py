#!/usr/bin/env python3
"""Tests for the ASD-STE100 prose linter.

Run from the repo root:

    python3 plugins/ste100-discussion/tests/test_lint.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, HOOKS)

from ste100_rules import (  # noqa: E402
    lint, mask, format_findings, RULES, RULE_NUMBERS,
)


def read_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return fh.read()


def rules_hit(findings):
    return {rule for _, rule, _ in findings}


class TestMasking(unittest.TestCase):
    """Exempt material must never reach a check."""

    def test_fenced_code_disappears(self):
        text = "Here is the fix.\n\n```python\nis_configured = True\n```\n"
        self.assertNotIn("is_configured", mask(text))

    def test_inline_code_becomes_one_word(self):
        self.assertEqual(mask("Call `a.b.c(x, y, z)` now.").strip(),
                         "Call  CODE  now.")

    def test_path_with_line_range_becomes_one_word(self):
        masked = mask("Look at lib/dispatch-stack.ts:118-124 today.")
        self.assertNotIn("dispatch-stack", masked)
        self.assertIn("PATH", masked)

    def test_bare_filename_becomes_one_word(self):
        self.assertIn("PATH", mask("Open callback.mjs and read it."))

    def test_url_becomes_one_word(self):
        masked = mask("See https://example.com/a/b?c=d for details.")
        self.assertNotIn("example.com", masked)

    def test_dotted_path_does_not_split_a_sentence(self):
        # A naive splitter would cut at ".ts" and hide the long sentence.
        text = ("The deploy step in lib/dispatch-stack.ts:61 passes the key "
                "to the worker and to the callback and to the notifier and "
                "to the retry queue as well.")
        self.assertIn("length", rules_hit(lint(text)))

    def test_table_rows_are_ignored(self):
        text = "| Path | Job |\n|---|---|\n| a.py | It is invoked by cron |\n"
        self.assertEqual(lint(text), [])


class TestChecks(unittest.TestCase):

    def test_flags_passive_voice(self):
        text = ("Credentials are hardcoded in the worker entry point. "
                "The key is stored there in plaintext by the build step.")
        self.assertIn("passive", rules_hit(lint(text)))

    def test_active_voice_passes(self):
        text = ("The worker entry point hardcodes the credentials. "
                "The build step writes the key there in plaintext.")
        self.assertEqual(lint(text), [])

    def test_flags_long_sentence(self):
        text = " ".join(["alpha"] * 30) + "."
        self.assertIn("length", rules_hit(lint(text)))

    def test_flags_gerund(self):
        text = ("The Lambda checks the header before invoking the worker. "
                "The worker then writes the label to the bucket.")
        self.assertIn("-ing form", rules_hit(lint(text)))

    def test_noun_modifier_ing_words_pass(self):
        # Same shape as a gerund, but these are not verbs.
        text = ("The callback accepts inbound tracking updates. "
                "The shipping provider signs each payload. "
                "A rising error rate wakes the on-call engineer.")
        self.assertEqual(lint(text), [])

    def test_worth_idiom_is_not_flagged(self):
        # A deliberate exemption, not an oversight. See _ING_TRIGGERS.
        text = ("Worth noting: the helper retries twice. "
                "One detail is worth flagging before you merge the branch.")
        self.assertEqual(lint(text), [])

    def test_allowlisted_ing_nouns_pass(self):
        text = ("The setting controls routing and caching. "
                "The string holds the region. Logging stays on during a retry.")
        self.assertEqual(lint(text), [])

    def test_adjectival_participles_are_not_passive(self):
        text = ("The helper is based on fetch. The scope is limited to one "
                "region. That path is used by nobody today.")
        self.assertNotIn("passive", rules_hit(lint(text)))

    def test_un_prefixed_adjectives_are_not_passive(self):
        # From the corpus pass: these describe a state, not an action.
        text = ("Your branch is untouched by the run. CI is unaffected. "
                "The retry budget is unchanged in every region.")
        self.assertNotIn("passive", rules_hit(lint(text)))

    def test_un_prefixed_true_passives_still_flag(self):
        # The allowlist is explicit for this reason: some "un-" words
        # really are verbs with a hidden actor.
        text = ("The bucket was unlocked by the deploy step. "
                "The agent then read every object in the bucket.")
        self.assertIn("passive", rules_hit(lint(text)))

    def test_compound_ing_adjectives_pass(self):
        text = ("That warning is pre-existing on the main branch. "
                "The helper is load-bearing for both Lambdas today.")
        self.assertEqual(lint(text), [])

    def test_short_reply_is_skipped(self):
        self.assertEqual(lint("Done. The tests are passing."), [])


class TestFixtures(unittest.TestCase):
    """The real regression: a violating report against its rewrite."""

    def test_violating_fixture_is_flagged(self):
        findings = lint(read_fixture("violating.md"))
        self.assertTrue(findings, "violating fixture produced no findings")
        self.assertEqual(rules_hit(findings),
                         {"length", "passive", "-ing form"})

    def test_violating_fixture_flags_the_opening_sentence(self):
        findings = lint(read_fixture("violating.md"))
        opening = [f for f in findings if "Credentials are hardcoded" in f[0]]
        self.assertTrue(opening, "did not flag the opening passive sentence")
        self.assertIn("passive", {rule for _, rule, _ in opening})

    def test_violating_fixture_does_not_flag_the_paths(self):
        findings = lint(read_fixture("violating.md"))
        for sentence, _, _ in findings:
            self.assertNotIn("dispatch-stack", sentence)
            self.assertNotIn("callback.mjs", sentence)

    def test_compliant_fixture_is_clean(self):
        findings = lint(read_fixture("compliant.md"))
        self.assertEqual(
            findings, [],
            "compliant rewrite was flagged:\n" +
            "\n".join("  [%s] %s" % (r, s) for s, r, _ in findings))


class TestRuleNumbering(unittest.TestCase):
    """The rules live in two files. They must not drift apart.

    `RULES` in ste100_rules.py and the output style are separate copies.
    The linter cites rule numbers from one while the model reads the
    other. A silent edit to either would make the hook cite a number
    that no longer means what it says.
    """

    STYLE = os.path.join(os.path.dirname(HERE), "output-styles",
                         "ASD-STE100.md")

    @staticmethod
    def numbered(text):
        return re.findall(r"^(\d+)\. (.+)$", text, re.M)

    def test_style_file_and_rules_string_agree(self):
        with open(self.STYLE, "r", encoding="utf-8") as fh:
            style = fh.read()
        self.assertEqual(self.numbered(style), self.numbered(RULES),
                         "output style and RULES have drifted apart")

    def test_rules_are_numbered_one_to_seven(self):
        nums = [int(n) for n, _ in self.numbered(RULES)]
        self.assertEqual(nums, list(range(1, 8)))

    def test_every_emitted_rule_number_exists(self):
        declared = {int(n) for n, _ in self.numbered(RULES)}
        for name, number in RULE_NUMBERS.items():
            self.assertIn(number, declared,
                          "linter cites rule %d (%s) but no such rule exists"
                          % (number, name))

    def test_rule_numbers_match_their_text(self):
        text = dict((int(n), t) for n, t in self.numbered(RULES))
        self.assertIn("20 words", text[RULE_NUMBERS["length"]])
        self.assertIn("Active voice", text[RULE_NUMBERS["passive"]])
        self.assertIn("-ing", text[RULE_NUMBERS["-ing form"]])

    def test_length_finding_does_not_impersonate_rule_2(self):
        # Rule 2 says 20 words; the linter fires at 25. The message must
        # name the lint floor, never imply that 25 is the rule.
        findings = lint(" ".join(["alpha"] * 30) + ".")
        detail = [d for _, r, d in findings if r == "length"][0]
        self.assertIn("lint floor", detail)
        self.assertNotIn("max", detail)
        self.assertIn("The rule is 20 words", format_findings(findings))

    def test_findings_cite_the_rule_number(self):
        findings = lint(read_fixture("violating.md"))
        message = format_findings(findings)
        for _, rule, _ in findings[:6]:
            self.assertIn("rule %d" % RULE_NUMBERS[rule], message)


class TestHooks(unittest.TestCase):
    """End-to-end over the two hook entry points."""

    def _run_lint_hook(self, payload, env=None):
        full_env = dict(os.environ)
        full_env.update(env or {})
        proc = subprocess.run(
            [sys.executable, os.path.join(HOOKS, "ste100_lint.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env=full_env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def _transcript(self, text, sidechain=False):
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8")
        fh.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        entry = {"type": "assistant",
                 "message": {"content": [{"type": "text", "text": text}]}}
        if sidechain:
            entry["isSidechain"] = True
        fh.write(json.dumps(entry) + "\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_reminder_hook_emits_the_rules(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HOOKS, "ste100_remind.py")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ASD-STE100", proc.stdout)
        self.assertIn("subagent", proc.stdout)
        self.assertIn("check every sentence against rules 1 to 7", proc.stdout)
        self.assertEqual(proc.stdout.strip(), RULES.strip())

    def test_reminder_hook_honours_opt_out(self):
        env = dict(os.environ, STE100_REMIND="0")
        proc = subprocess.run(
            [sys.executable, os.path.join(HOOKS, "ste100_remind.py")],
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.stdout, "")

    def test_default_mode_is_warn(self):
        # A Stop-hook block appends a second reply rather than replacing
        # the first. Warn must stay the default until that is worth it.
        path = self._transcript(read_fixture("violating.md"))
        out = json.loads(self._run_lint_hook({"transcript_path": path}))
        self.assertNotIn("decision", out)
        self.assertIn("ASD-STE100", out["systemMessage"])

    def test_lint_hook_blocks_when_block_mode_is_set(self):
        path = self._transcript(read_fixture("violating.md"))
        out = json.loads(self._run_lint_hook(
            {"transcript_path": path}, env={"STE100_LINT_MODE": "block"}))
        self.assertEqual(out["decision"], "block")
        self.assertIn("ASD-STE100", out["reason"])

    def test_lint_hook_allows_compliant_text(self):
        path = self._transcript(read_fixture("compliant.md"))
        self.assertEqual(self._run_lint_hook({"transcript_path": path}), "")

    def test_lint_hook_respects_the_loop_guard(self):
        path = self._transcript(read_fixture("violating.md"))
        out = self._run_lint_hook({"transcript_path": path,
                                   "stop_hook_active": True},
                                  env={"STE100_LINT_MODE": "block"})
        self.assertEqual(out, "", "hook blocked twice — infinite loop risk")

    def test_lint_hook_ignores_subagent_turns(self):
        path = self._transcript(read_fixture("violating.md"), sidechain=True)
        self.assertEqual(self._run_lint_hook({"transcript_path": path}), "")

    def test_lint_hook_warn_mode_never_blocks(self):
        path = self._transcript(read_fixture("violating.md"))
        out = json.loads(self._run_lint_hook(
            {"transcript_path": path}, env={"STE100_LINT_MODE": "warn"}))
        self.assertNotIn("decision", out)
        self.assertIn("ASD-STE100", out["systemMessage"])

    def test_lint_hook_off_mode_is_silent(self):
        path = self._transcript(read_fixture("violating.md"))
        self.assertEqual(
            self._run_lint_hook({"transcript_path": path},
                                env={"STE100_LINT_MODE": "off"}), "")

    def test_lint_hook_survives_a_broken_payload(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HOOKS, "ste100_lint.py")],
            input="not json", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_lint_hook_survives_a_missing_transcript(self):
        out = self._run_lint_hook({"transcript_path": "/no/such/file.jsonl"})
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
