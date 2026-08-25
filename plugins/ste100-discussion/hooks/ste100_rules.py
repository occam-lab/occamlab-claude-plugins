"""Shared ASD-STE100 rules text and prose linter.

Two hooks import this module:

  ste100_remind.py  -- UserPromptSubmit, injects RULES as extra context
  ste100_lint.py    -- Stop, lints the last assistant reply

Only three of the style rules are machine-checkable: sentence length,
passive voice, and -ing verb forms. "One meaning per word" and "no
dangling pronouns" stay in the style text, enforced by the model.

Standard library only. Python 3.8+.
"""

import os
import re

# --------------------------------------------------------------------------
# Rules text injected on every user prompt.
# --------------------------------------------------------------------------

RULES = """<ste100-reminder>
Write every prose explanation in ASD-STE100. These are hard rules:

1. One idea per sentence. Split a sentence that carries two.
2. Maximum 20 words per sentence.
3. Active voice. Name the actor: not "X is configured by Y" but "Y configures X".
4. Simple tenses. No "-ing" verb forms.
5. One meaning per word. Do not reuse a word for two senses in one reply.
6. No dangling pronouns. Restate the noun when "it" or "this" could be ambiguous.
7. Rewrite a subagent's prose into your own sentences. Never paste it through.

Before you send this reply, check every sentence against rules 1 to 7.

Exempt from every rule: code, diffs, commit messages, file paths, API names,
library names, and framework names.
</ste100-reminder>"""

# The rules a regex can check, and the number each one carries above.
# Rules 1, 5, 6, and 7 are not machine-checkable. They live in the text.
RULE_NUMBERS = {"length": 2, "passive": 3, "-ing form": 4}

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

# Rule 2 says 20 words. This linter fires at 25.
#
# The gap is deliberate. A regex cannot judge a 21-word sentence, and a
# hook that argues over one word teaches the model to discount it. So the
# lint floor sits above the rule, the way a formatter warns at 120
# columns under a 100-column style. Every finding says "lint floor" for
# that reason. It must never claim to be rule 2's own number.
#
# Set STE100_MAX_WORDS=20 to lint the rule exactly.
MAX_WORDS = int(os.environ.get("STE100_MAX_WORDS", "25"))

# Below this, a reply is an acknowledgement, not prose. Skip it.
MIN_PROSE_WORDS = int(os.environ.get("STE100_MIN_PROSE_WORDS", "15"))

# -ing tokens that are nouns, adjectives, or domain terms -- not gerunds.
ING_ALLOWLIST = {
    "string", "strings", "during", "thing", "things", "something", "nothing",
    "anything", "everything", "morning", "evening", "spring", "bring", "king",
    "ring", "sing", "wing", "ceiling", "meaning", "warning", "warnings",
    "setting", "settings", "binding", "bindings", "listing", "listings",
    "logging", "tracing", "routing", "polling", "caching", "encoding",
    "decoding", "mapping", "mappings", "padding", "heading", "headings",
    "landing", "building", "buildings", "engineering", "marketing",
    "billing", "onboarding", "tooling", "styling", "linting", "casing",
    "framing", "wording", "reading", "readings", "recording", "recordings",
    "training", "meeting", "meetings", "sibling", "siblings", "timing",
    "scaling", "sampling", "throttling", "streaming", "hosting", "pricing",
    "handling", "parsing", "escaping", "hashing", "signing", "pending",
    "missing", "existing", "following", "remaining", "outstanding",
    "leading", "trailing", "incoming", "outgoing", "long-running", "running",
    # Corpus pass: compound adjectives that the trigger rule alone misses,
    # because a be-verb sits directly before them.
    "pre-existing", "load-bearing", "long-standing", "standing",
    "self-hosting", "far-reaching", "ongoing", "upcoming",
}

# --------------------------------------------------------------------------
# Masking -- remove exempt material before any sentence is measured.
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_UNCLOSED_FENCE_RE = re.compile(r"```.*\Z", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_URL_RE = re.compile(r"<?\bhttps?://\S+", re.IGNORECASE)
# A path token: has a slash, or looks like name.ext, optionally with :line.
_PATH_RE = re.compile(
    r"\b(?:[\w.\-@]+/)+[\w.\-]+(?::\d+(?:-\d+)?)?"
    r"|\b\w[\w\-]*\.(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|rb|java|kt|sh|json|"
    r"yaml|yml|toml|md|html|css|sql|txt|lock|env)\b(?::\d+(?:-\d+)?)?"
)
_TABLE_LINE_RE = re.compile(r"^\s*\|.*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s.*$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][\w-]*[^>]*>")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)

# Abbreviations whose dot must not end a sentence.
_ABBREVS = ["e.g.", "i.e.", "etc.", "vs.", "approx.", "Mr.", "Dr.", "Fig.",
            "No.", "cf.", "et al."]


def mask(text):
    """Strip every ASD-STE100-exempt span from `text`.

    Each removed span becomes a single placeholder word. A placeholder
    carries no sentence-ending punctuation, so it cannot split a
    sentence or inflate a word count beyond one.
    """
    text = _FENCE_RE.sub("\n", text)
    text = _UNCLOSED_FENCE_RE.sub("\n", text)
    text = _TABLE_LINE_RE.sub("", text)
    text = _HEADING_RE.sub("", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" CODE ", text)
    text = _URL_RE.sub(" URL ", text)
    text = _PATH_RE.sub(" PATH ", text)
    text = _BULLET_RE.sub("", text)
    return text


def _split_sentences(text):
    """Split masked prose into sentences."""
    for i, abbrev in enumerate(_ABBREVS):
        text = text.replace(abbrev, "\x00%d\x00" % i)
    # A blank line ends a sentence even without punctuation.
    text = re.sub(r"\n\s*\n", ".\n", text)
    parts = re.split(r"(?<=[.!?:])[\s\n]+", text)
    out = []
    for part in parts:
        for i, abbrev in enumerate(_ABBREVS):
            part = part.replace("\x00%d\x00" % i, abbrev)
        part = " ".join(part.split())
        if part:
            out.append(part)
    return out


def _words(sentence):
    return [w for w in re.split(r"\s+", sentence) if re.search(r"[A-Za-z]", w)]


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

_PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+"
    r"(?:not\s+|already\s+|also\s+|only\s+|never\s+)?"
    r"(\w+(?:ed|en))\b",
    re.IGNORECASE,
)

# Past participles that are ordinary adjectives, not passive voice.
#
# The "un-" family below came out of a 9,396-sentence corpus pass over
# real transcripts. "Your branch is untouched" and "CI is unaffected"
# describe a state. No hidden actor exists to promote. An explicit list
# beats a blanket "un-" rule, because "was unlocked" and "is
# uninstalled" are true passives.
_PASSIVE_ALLOWLIST = {
    "used", "based", "supposed", "intended", "limited", "related",
    "advanced", "unexpected", "detailed", "mixed", "open", "broken",
    "given", "hidden", "written",
    "untouched", "unchanged", "unaffected", "unrelated", "unused",
    "uncommitted", "unresolved", "undocumented", "unfinished",
    "unstaged", "untracked", "unread", "unlimited", "unsorted",
}

_ING_RE = re.compile(r"\b([a-z][a-z\-]{2,}ing)\b")

# An "-ing" token is a verb form only in the right slot. English uses the
# same shape for noun modifiers ("tracking updates", "shipping provider")
# and for plain nouns ("the setting"). Flag the token only when one of
# these words comes directly before it. That keeps a blocking hook quiet.
_ING_TRIGGERS = {
    "am", "is", "are", "was", "were", "be", "been", "being",
    "by", "before", "after", "while", "whilst", "without", "upon",
    "despite", "instead", "risk", "risks",
    # "worth" is deliberately absent. ASD-STE100 does flag "worth noting",
    # and "Note X" is the better sentence. But the corpus pass showed the
    # idiom family drives 22% of this rule while it blocks only 6 replies
    # of ~1,790 on its own. The clutter outweighed the gain. Add "worth"
    # back here to enforce it.
    "avoid", "avoids", "avoided", "start", "starts", "started",
    "stop", "stops", "stopped", "keep", "keeps", "kept",
    "begin", "begins", "began", "continue", "continues", "continued",
    "consider", "considers", "prevent", "prevents", "finish", "finishes",
    "suggest", "suggests", "recommend", "recommends",
}


def _check_sentence(sentence):
    findings = []

    words = _words(sentence)
    if len(words) > MAX_WORDS:
        findings.append(("length", "%d words, over the %d-word lint floor"
                         % (len(words), MAX_WORDS)))

    m = _PASSIVE_RE.search(sentence)
    if m and m.group(2).lower() not in _PASSIVE_ALLOWLIST:
        findings.append(("passive", '"%s %s"' % (m.group(1), m.group(2))))

    for m in _ING_RE.finditer(sentence):
        token = m.group(1)
        if token in ING_ALLOWLIST:
            continue
        prev = re.search(r"([A-Za-z']+)\W+$", sentence[:m.start()])
        if not prev or prev.group(1).lower() not in _ING_TRIGGERS:
            continue
        findings.append(("-ing form", '"%s %s"' % (prev.group(1), token)))
        break

    return findings


def lint(text):
    """Return a list of (sentence, rule, detail) findings for `text`."""
    masked = mask(text)
    if len(_words(masked)) < MIN_PROSE_WORDS:
        return []

    findings = []
    for sentence in _split_sentences(masked):
        for rule, detail in _check_sentence(sentence):
            findings.append((sentence, rule, detail))
    return findings


def format_findings(findings, limit=6):
    """Render findings as a rewrite instruction for the model."""
    lines = [
        "Your reply breaks the ASD-STE100 rules this session requires.",
        "Rewrite the prose. Keep every fact, path, and code block unchanged.",
        "",
    ]
    for sentence, rule, detail in findings[:limit]:
        short = sentence if len(sentence) <= 160 else sentence[:157] + "..."
        lines.append("- [rule %d — %s: %s] %s"
                     % (RULE_NUMBERS[rule], rule, detail, short))
    if len(findings) > limit:
        lines.append("- ...and %d more." % (len(findings) - limit))

    broken = sorted({RULE_NUMBERS[r] for _, r, _ in findings})
    fixes = {2: "rule 2: split the sentence in two. The rule is 20 words;"
                " the lint floor above it is %d." % MAX_WORDS,
             3: "rule 3: name the actor and use active voice.",
             4: "rule 4: replace the \"-ing\" form with a simple tense."}
    lines.append("")
    for n in broken:
        lines.append(fixes[n])
    return "\n".join(lines)
