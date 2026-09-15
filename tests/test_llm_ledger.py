"""What was sent to which model, when, and at what cost.

Three properties carry the whole value of this record, and each is a way it
could quietly stop being worth anything.

It must record the model that **answered**, not the one configured, or a
cascade that escalated writes a document and the record names the wrong
model. It must record **no content**, or the ledger copies a licensed
export into a file under `output/` and becomes the leak it exists to
disprove. And it must **raise rather than drop** a write it cannot make, or
it reports a clean history of a run it never observed.

The rest is arithmetic, and the arithmetic has one trap of its own: a local
model costs 0.0 and a provider that does not price its calls costs None, and
a summary that folds those together reads an unpriced run as a free one.
"""

from __future__ import annotations

import json

import pytest

from policyforge.llm import ledger
from policyforge.llm.base import LLMResponse
from policyforge.llm.ledger import CallRecord, RecordingProvider, Totals


class FakeProvider:
    """A provider that answers with whatever it was handed."""

    def __init__(self, responses=None, raises=None):
        self._responses = list(responses or [LLMResponse(text="ok", model="fake-1")])
        self._raises = raises
        self.model = "configured-model"
        self.calls = []

    def generate(self, *, system, prompt, max_tokens=4096, temperature=0.2):
        self.calls.append({"system": system, "prompt": prompt})
        if self._raises:
            raise self._raises
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]

    def supports_schema(self):
        return True

    def generate_json(self, *, system, prompt, schema, **kwargs):
        return self.generate(system=system, prompt=prompt)

    def check(self):
        return True


def _recorder(tmp_path, inner=None, **kwargs):
    return RecordingProvider(
        inner or FakeProvider(),
        provider_name=kwargs.pop("provider_name", "litellm"),
        provider_class=kwargs.pop("provider_class", "third-party"),
        path=tmp_path / "calls.jsonl",
    )


# ---- what gets recorded ---------------------------------------------------


def test_a_call_is_recorded_with_its_model_and_cost(tmp_path):
    inner = FakeProvider(
        [
            LLMResponse(
                text="drafted",
                model="deepseek-v4-flash",
                input_tokens=120,
                output_tokens=40,
                cost_usd=0.0013,
            )
        ]
    )
    provider = _recorder(tmp_path, inner)

    provider.generate(system="S", prompt="P")

    records = ledger.load(tmp_path / "calls.jsonl")
    assert len(records) == 1
    assert records[0].model == "deepseek-v4-flash"
    assert records[0].provider == "litellm"
    assert records[0].provider_class == "third-party"
    assert records[0].input_tokens == 120
    assert records[0].cost_usd == pytest.approx(0.0013)


def test_the_model_recorded_is_the_one_that_answered(tmp_path):
    """Not the one in config.

    A cascade answers with its stronger half whenever the cheap one runs out
    of room, and `LLMResponse.model` is the only thing that knows which. A
    record naming the configured model would be false in precisely the case
    somebody later needs it to be true.
    """
    inner = FakeProvider([LLMResponse(text="x", model="deepseek-v4-pro")])
    inner.model = "deepseek-v4-flash -> deepseek-v4-pro"
    provider = _recorder(tmp_path, inner)

    provider.generate(system="S", prompt="P")

    assert ledger.load(tmp_path / "calls.jsonl")[0].model == "deepseek-v4-pro"


def test_no_prompt_or_reply_is_written_to_the_file(tmp_path):
    """The one property that makes this safe to keep.

    A ledger that quoted what it saw would take a licensed export that
    correctly went to a local model and copy it into a file under output/.
    """
    secret_system = "HITRUST CSF requirement 01.c verbatim"
    secret_prompt = "Category: Access Control, Requirement: unique user identification"
    provider = _recorder(tmp_path, FakeProvider([LLMResponse(text="a reply", model="m")]))

    provider.generate(system=secret_system, prompt=secret_prompt)

    raw = (tmp_path / "calls.jsonl").read_text(encoding="utf-8")
    assert secret_system not in raw
    assert secret_prompt not in raw
    assert "a reply" not in raw
    # A fingerprint is kept, so two runs can be told apart without either
    # being reconstructable from the file.
    assert ledger.load(tmp_path / "calls.jsonl")[0].prompt_sha


def test_the_prompt_hash_distinguishes_prompts_and_where_text_sits():
    """Moving a rule between the system and user prompt changes the digest.

    Which is right: for several of the models measured here, moving one rule
    is worth points in either direction, so the two prompts are not the same
    prompt.
    """
    a = ledger.prompt_digest("rule one", "question")
    b = ledger.prompt_digest("", "rule one question")
    c = ledger.prompt_digest("rule one", "question")

    assert a == c
    assert a != b


def test_a_failed_call_is_recorded_and_the_error_re_raised(tmp_path):
    """It reached the vendor, was billed, and carried its content there.

    A ledger that only recorded successes would undercount both the spend
    and the exposure, which are the two things it is for.
    """
    provider = _recorder(tmp_path, FakeProvider(raises=RuntimeError("rate limited")))

    with pytest.raises(RuntimeError):
        provider.generate(system="S", prompt="P")

    records = ledger.load(tmp_path / "calls.jsonl")
    assert len(records) == 1
    assert records[0].error == "RuntimeError"


def test_the_connectivity_probe_is_not_recorded(tmp_path):
    """`llm-check` sends a fixed two-word probe and sees no real content.

    Recording it would bury the calls that saw something under the ones that
    saw nothing.
    """
    provider = _recorder(tmp_path)

    assert provider.check()
    assert not (tmp_path / "calls.jsonl").exists()


def test_a_write_failure_raises_rather_than_being_swallowed(tmp_path, monkeypatch):
    """The difference between a control and a log.

    A ledger that reported a clean history of a run it did not observe is
    worse than no ledger, because somebody would rely on it.
    """
    provider = _recorder(tmp_path)

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "append", explode)

    with pytest.raises(OSError):
        provider.generate(system="S", prompt="P")


# ---- scopes ---------------------------------------------------------------


def test_calls_inside_a_scope_are_attributed_to_its_subject(tmp_path):
    provider = _recorder(tmp_path)

    with ledger.about("standard/authenticator-mgmt", site="generate") as scope:
        provider.generate(system="S", prompt="one")
        provider.generate(system="S", prompt="two")

    assert len(scope.records) == 2
    recorded = ledger.load(tmp_path / "calls.jsonl")
    assert {r.subject for r in recorded} == {"standard/authenticator-mgmt"}
    assert {r.site for r in recorded} == {"generate"}


def test_calls_outside_a_scope_are_recorded_with_no_subject(tmp_path):
    """Unattributed rather than guessed at.

    An entry saying "we do not know what this was about" is a true statement
    about a run. An invented one is not, and would be indistinguishable from
    a real attribution later.
    """
    provider = _recorder(tmp_path)

    provider.generate(system="S", prompt="P")

    assert ledger.load(tmp_path / "calls.jsonl")[0].subject is None


def test_scopes_nest_and_the_outer_one_resumes(tmp_path):
    provider = _recorder(tmp_path)

    with ledger.about("outer"):
        provider.generate(system="S", prompt="a")
        with ledger.about("inner"):
            provider.generate(system="S", prompt="b")
        provider.generate(system="S", prompt="c")

    subjects = [r.subject for r in ledger.load(tmp_path / "calls.jsonl")]
    assert subjects == ["outer", "inner", "outer"]


def test_a_scope_names_every_model_that_answered(tmp_path):
    """A cascade can write one document with two models, and both are true."""
    inner = FakeProvider(
        [
            LLMResponse(text="a", model="flash"),
            LLMResponse(text="b", model="pro"),
            LLMResponse(text="c", model="flash"),
        ]
    )
    provider = _recorder(tmp_path, inner)

    with ledger.about("standard/x") as scope:
        for _ in range(3):
            provider.generate(system="S", prompt="P")

    assert scope.models == ["flash", "pro"]


def test_provenance_is_small_and_names_what_wrote_the_document(tmp_path):
    inner = FakeProvider([LLMResponse(text="a", model="claude-sonnet-5", cost_usd=0.02)])
    provider = _recorder(tmp_path, inner, provider_name="anthropic")

    with ledger.about("policy/access-control", site="generate") as scope:
        provider.generate(system="S", prompt="P")

    stamp = scope.provenance()
    assert stamp["models"] == ["claude-sonnet-5"]
    assert stamp["calls"] == 1
    assert stamp["provider"] == "anthropic"
    assert stamp["cost_usd"] == pytest.approx(0.02)
    assert len(stamp["prompt_shas"]) == 1
    # It goes into every version-history entry, so it stays a stamp rather
    # than a copy of the ledger.
    assert set(stamp) <= {
        "models",
        "calls",
        "prompt_shas",
        "provider",
        "provider_class",
        "cost_usd",
        "content_class",
    }


def test_an_unpriced_scope_reports_no_cost_rather_than_zero(tmp_path):
    """Free and unknown are different answers."""
    provider = _recorder(tmp_path, FakeProvider([LLMResponse(text="a", model="m")]))

    with ledger.about("standard/x") as scope:
        provider.generate(system="S", prompt="P")

    assert scope.cost_usd is None
    assert "cost_usd" not in scope.provenance()


def test_a_local_model_reports_zero_rather_than_unknown(tmp_path):
    provider = _recorder(
        tmp_path, FakeProvider([LLMResponse(text="a", model="qwen3", cost_usd=0.0)])
    )

    with ledger.about("standard/x") as scope:
        provider.generate(system="S", prompt="P")

    assert scope.cost_usd == 0.0
    assert scope.provenance()["cost_usd"] == 0.0


# ---- reading it back ------------------------------------------------------


def test_a_torn_line_does_not_make_the_history_unreadable(tmp_path):
    """A run killed mid-write should cost one record, not all of them."""
    path = tmp_path / "calls.jsonl"
    good = CallRecord(
        timestamp="2026-09-14T00:00:00+00:00",
        provider="litellm",
        provider_class="third-party",
        model="m",
        subject="standard/x",
        site="generate",
    )
    path.write_text(good.as_json() + "\n" + '{"timestamp": "2026-' + "\n", encoding="utf-8")

    records = ledger.load(path)
    assert len(records) == 1
    assert records[0].subject == "standard/x"


def test_an_unknown_field_from_a_future_version_is_ignored(tmp_path):
    """So a newer ledger stays readable by an older checkout."""
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-09-14T00:00:00+00:00",
                "provider": "litellm",
                "provider_class": "local",
                "model": "m",
                "subject": None,
                "site": None,
                "effort": "high",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert ledger.load(path)[0].model == "m"


def test_totals_distinguish_unpriced_from_free():
    unpriced = Totals()
    unpriced.add(CallRecord("t", "p", "local", "m", None, None))
    assert unpriced.cost == "unpriced"

    free = Totals()
    free.add(CallRecord("t", "p", "local", "m", None, None, cost_usd=0.0))
    assert free.cost == "$0.0000"


def test_summaries_group_by_any_field():
    records = [
        CallRecord("t", "p", "local", "flash", "standard/a", "generate"),
        CallRecord("t", "p", "local", "pro", "standard/a", "generate"),
        CallRecord("t", "p", "local", "flash", "standard/b", "ssp"),
    ]

    by_model = ledger.summarize(records, "model")
    assert by_model["flash"].calls == 2
    assert by_model["pro"].calls == 1

    by_subject = ledger.summarize(records, "subject")
    assert by_subject["standard/a"].calls == 2

    rendered = ledger.format_summary(records, "site")
    assert "generate" in rendered and "ssp" in rendered


def test_unattributed_calls_are_grouped_under_a_visible_label():
    records = [CallRecord("t", "p", "local", "m", None, None)]
    assert "(unattributed)" in ledger.format_summary(records, "subject")


# ---- configuration --------------------------------------------------------


def test_the_ledger_is_on_unless_config_turns_it_off():
    assert ledger.ledger_enabled({})
    assert ledger.ledger_enabled({"llm": {}})
    assert not ledger.ledger_enabled({"llm": {"ledger": {"enabled": False}}})


def test_wrapping_is_skipped_when_it_is_turned_off():
    inner = FakeProvider()
    config = {"llm": {"provider": "anthropic", "ledger": {"enabled": False}}}

    assert ledger.wrap(inner, config) is inner


def test_wrapping_carries_the_provider_class_from_the_boundary(tmp_path):
    inner = FakeProvider()
    config = {
        "llm": {
            "provider": "local",
            "base_url": "http://localhost:11434/v1",
            "ledger": {"path": str(tmp_path / "calls.jsonl")},
        }
    }

    wrapped = ledger.wrap(inner, config)
    wrapped.generate(system="S", prompt="P")

    assert ledger.load(tmp_path / "calls.jsonl")[0].provider_class == "local"


def test_the_wrapper_passes_through_attributes_of_the_provider_inside(tmp_path):
    """So a cascade's escalation counters stay visible to the eval meter.

    `_Metered.summary()` reaches for `escalations` and `primary_calls`; an
    opaque wrapper would make a working cascade indistinguishable from a
    dead one, which is the regression that counter was added to fix.
    """
    inner = FakeProvider()
    inner.escalations = 3
    inner.primary_calls = 40

    wrapped = _recorder(tmp_path, inner)

    assert wrapped.escalations == 3
    assert wrapped.primary_calls == 40
    assert wrapped.inner is inner
