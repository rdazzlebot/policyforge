"""zardoz answering tests (milestone M3) — grounded, or absent.

No test calls a model. The provider interface is one method, so a fake that
returns a scripted string exercises every path that matters, and the paths
that matter are mostly the *checks* — what happens when the model cites a
passage that was never supplied, or quotes text that is not in the source.

Those checks are the point of the module. A prompt asking a model to cite
its claims is a request; verifying the citations afterwards is the only
part that holds when the request is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from policyforge.zardoz.answer import (
    REFUSAL_SENTINEL,
    answer_question,
    build_prompt,
    check_answer,
)
from policyforge.zardoz.corpus import SUPPORTING, TRUSTED, Corpus
from policyforge.zardoz.corpus import CorpusDocument as Doc
from policyforge.zardoz.retrieve import build_index

ACCESS_STANDARD = """# Access Control Standard

## 4. Policy

### 4.1 Account Review

Account entitlements must be recertified quarterly by the system owner.
Terminated accounts are disabled within 24 hours. [NIST AC-2]
"""

RUNBOOK = """# Offboarding Runbook

Revoke the badge, then close the Okta account.
"""


@dataclass
class FakeResponse:
    text: str
    model: str = "fake"


class FakeProvider:
    """Returns a scripted answer and records what it was asked."""

    def __init__(self, reply: str = "") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    def generate(self, *, system, prompt, max_tokens=4096, temperature=0.2):
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return FakeResponse(self.reply)

    def check(self) -> bool:
        return True


class ExplodingProvider:
    def generate(self, **kwargs):
        raise RuntimeError("connection reset")

    def check(self) -> bool:
        return False


def _corpus():
    return Corpus(
        documents=[
            Doc(
                doc_id="standards-access-control",
                title="Access Control Standard",
                space="",
                confidence=TRUSTED,
                source="markdown",
                path="standards/access-control.md",
                tier="standard",
                topic="Access Review",
                owner="IAM Engineering",
                body=ACCESS_STANDARD,
            ),
            Doc(
                doc_id="eng-offboarding-runbook",
                title="Offboarding Runbook",
                space="ENG",
                confidence=SUPPORTING,
                webui_url="https://x/wiki/offboarding",
                body=RUNBOOK,
            ),
        ]
    )


def _passages(query="how often are accounts recertified?"):
    return build_index(_corpus()).search(query)


# --------------------------------------------------------------------------
# The model is not always called
# --------------------------------------------------------------------------


def test_no_passages_means_the_model_is_never_asked():
    """A model handed a question and no context answers it from what access
    control standards usually say. That is the failure this whole package
    exists to prevent, and it arrives sounding entirely plausible."""
    provider = FakeProvider("Accounts are reviewed annually.")

    answer = answer_question("what is our vacation policy?", [], provider)

    assert provider.calls == [], "the provider was called with nothing to ground on"
    assert answer.refused
    assert "Nothing in the synced documents" in answer.text


def test_the_refusal_token_becomes_a_plain_refusal():
    provider = FakeProvider(REFUSAL_SENTINEL)

    answer = answer_question("what is the RTO?", _passages(), provider)

    assert answer.refused
    assert REFUSAL_SENTINEL not in answer.text
    assert "do not answer that" in answer.text
    assert answer.passages, "the closest passages are still offered"


def test_answering_is_deterministic():
    """The same question over the same documents must not give two accounts
    of what the organization requires."""
    provider = FakeProvider("Quarterly. [1]")

    answer_question("how often?", _passages(), provider)

    assert provider.calls[0]["temperature"] == 0.0


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def test_passages_are_numbered_as_the_answer_will_cite_them():
    prompt = build_prompt("how often?", _passages())

    assert "[1] Access Control Standard § 4. Policy > 4.1 Account Review" in prompt
    assert "recertified quarterly" in prompt


def test_the_prompt_says_which_passages_nobody_owns():
    """A requirement nobody is accountable for is a different kind of fact
    from one a named team owns, and the answer has to be able to say so."""
    prompt = build_prompt("how is offboarding done?", _passages("revoke badge okta account"))

    assert "supporting (no declared owner)" in prompt


# --------------------------------------------------------------------------
# Verifying what came back
# --------------------------------------------------------------------------


def test_a_well_formed_answer_passes_its_checks():
    passages = _passages()

    cited, warnings = check_answer("Entitlements are recertified quarterly. [1]", passages)

    assert cited == [1]
    assert warnings == []


def test_a_citation_to_a_passage_that_was_never_supplied_is_caught():
    """The model is told to cite; it is not trusted to have cited something
    real. A marker pointing at nothing is a fabricated source."""
    passages = _passages()

    cited, warnings = check_answer("Reviews happen quarterly. [9]", passages)

    assert cited == [9]
    assert any("never" in w and "[9]" in w for w in warnings)


def test_an_answer_with_no_citations_at_all_is_flagged():
    passages = _passages()

    _, warnings = check_answer("Accounts are reviewed every quarter.", passages)

    assert any("without citing" in w for w in warnings)


def test_a_quotation_that_is_not_verbatim_is_caught():
    """A quotation is what somebody pastes into a ticket or shows an
    assessor. If it isn't in the document, that is the most damaging thing
    this tool could emit."""
    passages = _passages()

    _, warnings = check_answer(
        'The Standard says "entitlements shall be recertified twice yearly" [1]', passages
    )

    assert any("appears in no passage" in w for w in warnings)


def test_a_verbatim_quotation_passes():
    passages = _passages()

    _, warnings = check_answer(
        'It says "Account entitlements must be recertified quarterly" [1]', passages
    )

    assert warnings == []


def test_short_quoted_phrases_are_not_treated_as_quotations():
    """Models quote for mention as well as quotation — the "Owner" field, a
    "trusted" document. Flagging those trains the reader to ignore the
    warning that matters."""
    passages = _passages()

    _, warnings = check_answer('The "owner" recertifies them quarterly. [1]', passages)

    assert warnings == []


def test_whitespace_differences_do_not_make_a_quotation_wrong():
    """The passage wraps mid-sentence; the answer will not."""
    passages = _passages()

    _, warnings = check_answer('It says "recertified quarterly by the system owner" [1]', passages)

    assert warnings == []


def test_warnings_survive_onto_the_answer():
    provider = FakeProvider("Reviews are annual. [7]")

    answer = answer_question("how often?", _passages(), provider)

    assert not answer.is_grounded
    assert answer.warnings


# --------------------------------------------------------------------------
# In the shell
# --------------------------------------------------------------------------


def _state(provider=None, note=""):
    from policyforge.zardoz.shell import ShellState

    return ShellState(corpus=_corpus(), provider=provider, provider_note=note)


def test_an_answer_is_shown_with_the_sources_it_cited():
    from policyforge.zardoz.shell import dispatch

    provider = FakeProvider("Entitlements are recertified quarterly. [1]")

    output = dispatch("how often are accounts recertified?", _state(provider))

    assert "recertified quarterly. [1]" in output
    assert "Sources:" in output
    assert "[1] Access Control Standard § 4. Policy > 4.1 Account Review" in output


def test_a_failed_check_is_shown_above_the_answer_not_below_it():
    """An integrity problem is only useful if the reader sees it before they
    believe the sentence it is about."""
    from policyforge.zardoz.shell import dispatch

    provider = FakeProvider("Reviews are annual. [7]")

    output = dispatch("how often are accounts recertified?", _state(provider))

    assert output.startswith("!!")
    assert output.index("did not pass its own checks") < output.index("Reviews are annual")


def test_with_no_model_configured_the_passages_are_shown_instead():
    """Retrieval is offline. An API key should not be the price of searching
    your own documents."""
    from policyforge.zardoz.shell import dispatch

    output = dispatch("how often are accounts recertified?", _state(note="No config/config.yaml"))

    assert "No config/config.yaml" in output
    assert "4.1 Account Review" in output
    assert "recertified quarterly" in output


def test_a_provider_failure_does_not_end_the_session():
    from policyforge.zardoz.shell import ShellState, dispatch

    state = ShellState(corpus=_corpus(), provider=ExplodingProvider())

    output = dispatch("how often are accounts recertified?", state)

    assert "could not be reached" in output
    assert "connection reset" in output
    assert state.running, "the shell keeps going"
    assert "4.1 Account Review" in output, "the passages are still offered"


def test_sources_shows_the_full_text_behind_the_last_answer():
    from policyforge.zardoz.shell import dispatch

    state = _state(FakeProvider("Recertified quarterly. [1]"))
    dispatch("how often are accounts recertified?", state)

    output = dispatch("/sources", state)

    assert "Terminated accounts are disabled within 24 hours" in output


def test_sources_before_any_question_says_so():
    from policyforge.zardoz.shell import dispatch

    assert "ask a question first" in dispatch("/sources", _state(FakeProvider()))


def test_a_refusal_still_offers_the_closest_passages():
    from policyforge.zardoz.shell import dispatch

    provider = FakeProvider(REFUSAL_SENTINEL)

    output = dispatch("how often are accounts recertified?", _state(provider))

    assert "do not answer that" in output
    assert "Closest passages:" in output


@pytest.mark.parametrize("reply", ["", "   \n  "])
def test_an_empty_reply_is_treated_as_ungrounded(reply):
    provider = FakeProvider(reply)

    answer = answer_question("how often?", _passages(), provider)

    assert answer.warnings, "an empty answer cites nothing and must say so"


def test_the_shell_opens_with_no_api_key_at_all(tmp_path, monkeypatch):
    """Running without a model is a supported mode, not a crash.

    `AnthropicProvider` raises RuntimeError for a missing key, and the shell
    caught only ValueError — so `policyforge zardoz` died on launch for
    anyone without a key. Invisible for as long as everybody working on it
    had one, which is exactly how this class of bug survives.
    """
    from click.testing import CliRunner

    import policyforge.cli as cli_mod

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        cli_mod,
        "load_config",
        lambda: {
            "llm": {"provider": "anthropic", "model": "m", "api_key_env": "ANTHROPIC_API_KEY"}
        },
    )

    result = CliRunner().invoke(
        cli_mod.cli,
        ["zardoz", "--no-art", "--corpus-dir", str(tmp_path / "absent")],
        input="/quit\n",
    )

    assert result.exit_code == 0, result.output
    assert "No model configured" in result.output
    assert "passages, not prose" in result.output
