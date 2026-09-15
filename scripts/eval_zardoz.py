#!/usr/bin/env python3
"""Run the graded eval cases against your configured model.

    python scripts/eval_zardoz.py --repeat 5
    python scripts/eval_zardoz.py --suite routing --repeat 20
    python scripts/eval_zardoz.py --dry-run

Comparing models is the other reason to run this. `--model` takes a LiteLLM
model string and ignores config.yaml, so a sweep is a shell loop rather than
a config file per candidate:

    for m in anthropic/claude-sonnet-5 ollama_chat/qwen3:14b; do
        python scripts/eval_zardoz.py --model "$m" --suite routing --repeat 3
    done

The report then carries what the run cost as well as what it scored, because
a pass rate without a price does not decide anything. A local model reports
0.0 and a provider that cannot say reports nothing at all — those are
different answers and the report keeps them apart.

Costs real money and needs network, which is why it is not part of
`scripts/check.py`. The prompts are the only part of this project that
cannot be tested against fixtures — whether the answerer refuses, whether
the router picks correctly, whether the rewriter invents a detail are all
properties of a model's behaviour.

`--repeat` is the point. A routing bug measured at one failure in eight came
back clean on its first two probes; graded once per case it would have
shipped. The report is a rate, and a case that passes seven times in eight
is reported as flaky rather than as passing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.runner import SUITES, format_report, load_cases, load_corpora, run_case

# The report quotes what the model said, and models return characters a
# Windows console cannot encode — a non-breaking hyphen is enough. Printing
# one raised UnicodeEncodeError *after* every call had been made and billed,
# destroying the report of a run that had completed: 78 requests spent, one
# traceback, no numbers. This project keeps a list of runs that say nothing;
# losing one to a console codec does not belong on it.
#
# Reconfigured rather than left to PYTHONIOENCODING, because the person who
# needs it is the one who has not hit this yet.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


class _Metered:
    """Wraps a provider and counts what the run spent.

    A pass rate on its own does not decide between two models — the whole
    question is what each one costs to be that good. Kept here rather than
    in the provider layer because it is a property of a *run*, and only the
    thing driving the run can see the whole of one.
    """

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0
        self.cost = 0.0
        #: True once any call priced itself. Distinguishes "this run was
        #: free" from "nobody reported a price", which a bare 0.0 cannot.
        self.priced = False
        #: Calls that raised. They reached the vendor and were billed, but
        #: no response came back to read a price off.
        self.unpriced = 0

    def generate(self, **kwargs):
        # Counted in a finally, because a call that raises was still sent and
        # still billed. Incrementing after the call instead let a model that
        # trips ReasoningBudgetExhausted report *fewer* calls and a *lower*
        # cost than one that answers cleanly — inverting the comparison the
        # meter exists to make, the same way `0.0 or None` did.
        try:
            response = self._inner.generate(**kwargs)
        except Exception:
            self.unpriced += 1
            raise
        finally:
            self.calls += 1
        if response.cost_usd is not None:
            self.cost += response.cost_usd
            self.priced = True
        return response

    def check(self) -> bool:
        return self._inner.check()

    def summary(self) -> str:
        if not self.priced:
            return f"{self.calls} model call(s); this provider does not report cost"
        each = self.cost / self.calls if self.calls else 0.0
        line = f"{self.calls} model call(s), ${self.cost:.4f} total, ${each:.5f} each"
        # A cascade's whole economic case is how rarely the cheap model
        # needed help. The counter existed and nothing printed it, which
        # made a working cascade indistinguishable from a dead one.
        escalations = getattr(self._inner, "escalations", None)
        if escalations is not None:
            primary = getattr(self._inner, "primary_calls", 0)
            share = f"{escalations / primary:.0%}" if primary else "n/a"
            line += f"; {escalations}/{primary} escalated to the stronger model ({share})"
        if self.unpriced:
            # Said out loud rather than folded in: the total is a floor, and
            # a reader comparing two models needs to know which way it is
            # wrong.
            line += f" (+{self.unpriced} call(s) that raised, billed but unpriced)"
        return line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), action="append", default=None)
    parser.add_argument("--repeat", type=int, default=3, help="runs per case (default: 3)")
    parser.add_argument("--limit", type=int, default=None, help="cap cases per suite")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would run, and call nothing"
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.0,
        help=(
            "seconds to hold between requests, for a model whose per-minute cap is low "
            "enough that retries alone still land inside the same window "
            "(cohere/command-a needs about 2)"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "LiteLLM model string to grade instead of the configured provider, "
            "e.g. anthropic/claude-sonnet-5, ollama_chat/qwen3:14b, gemini/gemini-2.0-flash. "
            'Needs the litellm extra: pip install "policyforge[litellm]"'
        ),
    )
    args = parser.parse_args()

    cases = load_cases(args.cases) if args.cases else load_cases()
    corpora = load_corpora(args.cases) if args.cases else load_corpora()
    wanted = args.suite or sorted(SUITES)
    planned = [
        (suite, case)
        for suite in wanted
        for case in (cases.get(suite, [])[: args.limit] if args.limit else cases.get(suite, []))
    ]

    if not planned:
        print("No cases selected.")
        return 1

    if args.dry_run:
        print(f"{len(planned)} case(s) x {args.repeat} run(s) = {len(planned) * args.repeat} calls")
        for suite, case in planned:
            print(f"  {suite:11} {case.get('name') or case.get('question')}")
        return 0

    if args.model:
        from policyforge.llm.litellm_provider import LiteLLMProvider

        provider = _Metered(
            LiteLLMProvider(model=args.model, min_interval_seconds=args.min_interval)
        )
        grading = args.model
    else:
        from policyforge.config import load_config
        from policyforge.llm.base import get_provider

        config = load_config()
        provider = _Metered(get_provider(config))
        model = getattr(provider._inner, "model", config["llm"].get("model", "?"))
        grading = f"{config['llm']['provider']} / {model}"

    # One cheap call before spending a whole run. Several of the paths under
    # test swallow provider failures on purpose — route() falls back to
    # keyword matching, expand_query returns nothing — so a dead API does
    # not raise. It quietly grades the fallback and reports a clean pass,
    # which is worse than an error because it looks like evidence. Measured:
    # with an exhausted balance the routing suite reported 11 of 11.
    try:
        provider.generate(system="Reply with one word.", prompt="ok?", max_tokens=64)
    except Exception as exc:  # noqa: BLE001 - any failure means do not proceed
        print(f"The API is not reachable, so nothing was run:\n  {exc}")
        return 2

    print(f"Running {len(planned)} case(s) x {args.repeat} against {grading}...\n")

    results = []
    for suite, case in planned:
        result = run_case(suite, case, provider, repeat=args.repeat, corpora=corpora)
        results.append(result)
        mark = (
            "!"
            if result.errors
            else ("." if result.rate == 1.0 else ("~" if result.flaky else "x"))
        )
        print(mark, end="", flush=True)
    print("\n")
    print(format_report(results, repeat=args.repeat))
    print(f"\n{provider.summary()}")

    # Flaky is a failure. The whole reason this exists is that a case which
    # is right most of the time is indistinguishable, from one run, from a
    # case that is right always.
    # An exit code of 2 for "could not run" so a caller can tell a dead key
    # from a regression. 1 stays the graded failure.
    if any(r.errors for r in results):
        return 2
    return 1 if any(r.rate < 1.0 for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
