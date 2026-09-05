#!/usr/bin/env python3
"""Run the graded eval cases against your configured model.

    python scripts/eval_zardoz.py --repeat 5
    python scripts/eval_zardoz.py --suite routing --repeat 20
    python scripts/eval_zardoz.py --dry-run

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), action="append", default=None)
    parser.add_argument("--repeat", type=int, default=3, help="runs per case (default: 3)")
    parser.add_argument("--limit", type=int, default=None, help="cap cases per suite")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would run, and call nothing"
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

    from policyforge.config import load_config
    from policyforge.llm.base import get_provider

    provider = get_provider(load_config())
    print(f"Running {len(planned)} case(s) x {args.repeat} against the configured model...\n")

    results = []
    for suite, case in planned:
        result = run_case(suite, case, provider, repeat=args.repeat, corpora=corpora)
        results.append(result)
        mark = "." if result.rate == 1.0 else ("~" if result.flaky else "x")
        print(mark, end="", flush=True)
    print("\n")
    print(format_report(results, repeat=args.repeat))

    # Flaky is a failure. The whole reason this exists is that a case which
    # is right most of the time is indistinguishable, from one run, from a
    # case that is right always.
    return 1 if any(r.rate < 1.0 for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
