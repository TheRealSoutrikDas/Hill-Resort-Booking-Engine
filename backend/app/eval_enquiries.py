"""Evaluate the enquiry classifier on the sample file (A-138 to A-144, D-46).

    python -m app.eval_enquiries                      # the configured backend
    python -m app.eval_enquiries --backend both       # keyword, then the model
    python -m app.eval_enquiries --backend gemini --out ../docs/eval/gemini-report.md

Each sample goes through `propose()`, the same function the pipeline uses for steps 2
to 5 (keyword classifier, model, lane in code, GM alert rule), so the numbers measure
the real rules. Nothing is written to the database. The report lists enquiry ids and
tags only, never message text (A-142).

Exit code 1 if any enquiry that must alert the GM does not (A-140). Accuracy has no pass
mark: the report shows the numbers and people judge them.
"""

import argparse
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.classifiers.base import EnquiryClassifier
from app.classifiers.keyword import KeywordClassifier
from app.classifiers.registry import get_model_backend
from app.core.config import Settings, get_settings
from app.db.models.enums import Lane
from app.enquiry_samples import (
    SAMPLE_ENQUIRIES_PATH,
    SampleEnquiry,
    SampleEnquiryFile,
    load_sample_enquiries,
)
from app.services.enquiry_lanes import LANE_FOR
from app.services.enquiry_pipeline import Proposal, propose

DEFAULT_DELAY_S = 4.5  # between model calls; about 13 a minute (A-141)
FIELD_NAMES = ("check_in", "check_out", "event_month", "guests", "nights", "budget_inr")


# ---------- scoring one sample (A-139) ----------


@dataclass(frozen=True)
class SampleScore:
    id: str
    tags: tuple[str, ...]
    expected_category: str
    category: str
    category_ok: bool
    secondary_ok: bool  # matched the sample's acceptable second category instead
    expected_lane: str
    lane: str
    lane_ok: bool
    must_alert: bool
    alerted: bool
    fields_right: tuple[str, ...]
    fields_wrong: tuple[str, ...]  # expected a value, got a different one
    fields_missing: tuple[str, ...]  # expected a value, got none
    fields_extra: tuple[str, ...]  # a value the sample does not list (shown, not counted)
    backend: str
    is_fallback: bool
    error: str | None
    seconds: float

    @property
    def alert_missed(self) -> bool:
        return self.must_alert and not self.alerted

    @property
    def false_alert(self) -> bool:
        return self.alerted and not self.must_alert


def lane_ok(sample: SampleEnquiry, lane: str) -> bool:
    if sample.expected_lane == "either":
        return True
    if sample.expected_lane == "unsorted":
        return lane == Lane.UNSORTED
    return lane == LANE_FOR[sample.expected_category]


def score(sample: SampleEnquiry, proposal: Proposal, seconds: float = 0.0) -> SampleScore:
    expected = sample.expected_fields.model_dump(exclude_none=True)
    got = proposal.final.fields.model_dump(exclude_none=True)
    right, wrong, missing = [], [], []
    for name in FIELD_NAMES:
        if name not in expected:
            continue
        if name not in got:
            missing.append(name)
        elif got[name] == expected[name]:
            right.append(name)
        else:
            wrong.append(name)
    extra = sorted(k for k in got if k in FIELD_NAMES and k not in expected)
    category = proposal.final.category
    return SampleScore(
        id=sample.id,
        tags=tuple(sample.tags),
        expected_category=sample.expected_category,
        category=category,
        category_ok=category == sample.expected_category,
        secondary_ok=sample.secondary_category is not None
        and category == sample.secondary_category,
        expected_lane=sample.expected_lane,
        lane=proposal.lane,
        lane_ok=lane_ok(sample, proposal.lane),
        must_alert=sample.must_alert_gm,
        alerted=bool(proposal.complaint_by),
        fields_right=tuple(right),
        fields_wrong=tuple(wrong),
        fields_missing=tuple(missing),
        fields_extra=tuple(extra),
        backend=proposal.final.backend,
        is_fallback=proposal.is_fallback,
        error=proposal.error,
        seconds=seconds,
    )


# ---------- a whole run ----------


@dataclass
class RunResult:
    label: str
    model_name: str
    scores: list[SampleScore] = field(default_factory=list)

    def count(self, predicate: Callable[[SampleScore], bool]) -> int:
        return sum(1 for s in self.scores if predicate(s))

    @property
    def alerts_missed(self) -> list[str]:
        return [s.id for s in self.scores if s.alert_missed]


def evaluate(
    samples: SampleEnquiryFile,
    *,
    keyword: EnquiryClassifier,
    model: EnquiryClassifier,
    threshold: float,
    label: str,
    delay_s: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    timer: Callable[[], float] = time.perf_counter,
) -> RunResult:
    result = RunResult(label=label, model_name=getattr(model, "model", model.name))
    calls_model = model.name != keyword.name
    for index, sample in enumerate(samples.enquiries):
        if calls_model and index and delay_s:
            sleep(delay_s)  # stay under the provider's per-minute limit (A-141)
        start = timer()
        proposal = propose(
            sample.message,
            samples.default_received_on,
            keyword=keyword,
            model=model,
            threshold=threshold,
        )
        result.scores.append(score(sample, proposal, timer() - start))
    return result


# ---------- the report ----------


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def _yes(flag: bool) -> str:
    return "yes" if flag else "**no**"


def render(results: Sequence[RunResult], samples: SampleEnquiryFile, source: str) -> str:
    n = len(samples.enquiries)
    brief = sum(1 for e in samples.enquiries if e.source == "brief")
    lines = [
        "# Enquiry classifier evaluation",
        "",
        f"Sample file: `{source}`, {n} enquiries ({brief} from the client brief, "
        f"{n - brief} invented), received on {samples.default_received_on.isoformat()}.",
        "",
        "How to read this: category is an exact match with the expected category; lane "
        "`auto` must reach the category's lane, `unsorted` must reach Unsorted, `either` "
        "always passes; a field counts when the sample lists it. A missed required GM "
        "alert fails the run (A-139, A-140).",
        "",
    ]
    if any(r.label == "keyword" for r in results):
        lines += [
            "> The keyword rules were written from these same messages, so the keyword "
            "figures are in-sample and flatter it. A model run is the fairer test (A-144).",
            "",
        ]
    lines += ["## Summary", ""]
    header = "| | " + " | ".join(r.label for r in results) + " |"
    lines += [header, "|---|" + "---|" * len(results)]

    def row(name: str, cell: Callable[[RunResult], str]) -> None:
        lines.append(f"| {name} | " + " | ".join(cell(r) for r in results) + " |")

    row("Model", lambda r: f"`{r.model_name}`")
    row("Category right", lambda r: _pct(r.count(lambda s: s.category_ok), n))
    row("Lane right", lambda r: _pct(r.count(lambda s: s.lane_ok), n))
    row(
        "Required GM alerts raised",
        lambda r: _pct(
            r.count(lambda s: s.must_alert and s.alerted), r.count(lambda s: s.must_alert)
        ),
    )
    row("False GM alerts", lambda r: str(r.count(lambda s: s.false_alert)))

    def fields(r: RunResult) -> str:
        right = sum(len(s.fields_right) for s in r.scores)
        listed = right + sum(len(s.fields_wrong) + len(s.fields_missing) for s in r.scores)
        return _pct(right, listed)

    row("Expected fields right", fields)
    row("Fell back to keywords", lambda r: str(r.count(lambda s: s.is_fallback)))

    def latency(r: RunResult) -> str:
        if r.label == "keyword":
            return "n/a"
        times = [s.seconds for s in r.scores if not s.is_fallback]
        return f"{statistics.median(times):.2f} s" if times else "n/a"

    row("Median time per enquiry", latency)
    row(
        "Gate (no missed alert)",
        lambda r: "pass" if not r.alerts_missed else f"**fail**: {', '.join(r.alerts_missed)}",
    )

    for r in results:
        lines += [
            "",
            f"## {r.label}: per enquiry",
            "",
            "| Id | Tags | Expected | Got | Category | Lane | GM alert | Fields wrong | "
            "Fields missing | Extra fields | Note |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for s in r.scores:
            alert = "yes" if s.alerted else "no"
            if s.alert_missed:
                alert = "**missed**"
            elif s.false_alert:
                alert = "yes (not required)"
            note = []
            if s.secondary_ok:
                note.append("matched the second category")
            if s.is_fallback:
                note.append(f"fallback: {s.error}")
            elif s.error:
                note.append(s.error)
            lines.append(
                f"| {s.id} | {', '.join(s.tags)} | {s.expected_category} ({s.expected_lane}) "
                f"| {s.category} / {s.lane} | {_yes(s.category_ok)} | {_yes(s.lane_ok)} "
                f"| {alert} | {', '.join(s.fields_wrong) or '-'} "
                f"| {', '.join(s.fields_missing) or '-'} | {', '.join(s.fields_extra) or '-'} "
                f"| {'; '.join(note) or '-'} |"
            )
    return "\n".join(lines) + "\n"


# ---------- command ----------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.eval_enquiries", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--backend",
        choices=("configured", "keyword", "gemini", "both"),
        default="configured",
        help="which backend to evaluate; 'both' runs keyword, then Gemini",
    )
    parser.add_argument("--file", type=Path, default=SAMPLE_ENQUIRIES_PATH)
    parser.add_argument("--out", type=Path, help="also write the report to this file")
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_S, help="seconds between model calls"
    )
    return parser.parse_args(argv)


def backends(choice: str, settings: Settings) -> list[tuple[str, EnquiryClassifier]]:
    """configured: what .env sets; keyword: no model; gemini: Gemini; both: keyword, then
    Gemini. Gemini always needs LLM_API_KEY (A-130); without it this raises ValueError."""
    keyword = KeywordClassifier()
    if choice == "configured":
        model = get_model_backend(settings)
        return [(model.name, model)]
    if choice == "keyword":
        return [("keyword", keyword)]
    if settings.classifier_backend != "gemini":
        settings = Settings.model_validate(
            {**settings.model_dump(), "classifier_backend": "gemini"}
        )
    gemini = get_model_backend(settings)
    return [("keyword", keyword), ("gemini", gemini)] if choice == "both" else [("gemini", gemini)]


def _reason(exc: ValueError) -> str:
    """One readable line from a settings ValidationError (or any ValueError)."""
    errors = getattr(exc, "errors", None)
    return errors()[0]["msg"].removeprefix("Value error, ") if errors else str(exc)


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    model_override: EnquiryClassifier | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    args = parse_args(argv)
    if settings is None:
        try:
            settings = get_settings()
        except ValueError as exc:
            print(f"Cannot evaluate: {_reason(exc)}", file=sys.stderr)
            return 2
    samples = load_sample_enquiries(args.file)
    keyword = KeywordClassifier()
    if model_override is not None:  # tests
        runs = [("keyword", keyword)] if args.backend == "both" else []
        runs.append((model_override.name, model_override))
    else:
        try:
            runs = backends(args.backend, settings)
        except ValueError as exc:
            print(f"Cannot evaluate: {_reason(exc)}", file=sys.stderr)
            return 2
    results = []
    for label, model in runs:
        print(f"Evaluating {label} on {len(samples.enquiries)} enquiries...", file=sys.stderr)
        results.append(
            evaluate(
                samples,
                keyword=keyword,
                model=model,
                threshold=settings.classifier_confidence_threshold,
                label=label,
                delay_s=args.delay,
                sleep=sleep,
            )
        )
    try:
        shown = args.file.resolve().relative_to(Path.cwd().resolve().parent)
    except ValueError:
        shown = args.file.name
    report = render(results, samples, str(shown))
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    missed = [(r.label, r.alerts_missed) for r in results if r.alerts_missed]
    for label, ids in missed:
        print(
            f"FAIL ({label}): required GM alerts not raised for {', '.join(ids)}", file=sys.stderr
        )
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
