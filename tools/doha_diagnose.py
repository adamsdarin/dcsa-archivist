"""Summarise a DOHA intake plan and re-check: exception reasons, unsettled rulings, topic
disagreement patterns, outcome conflicts; optionally print text samples for one reason.

    python tools/doha_diagnose.py --plan <plan dir> --recheck <recheck dir>
    python tools/doha_diagnose.py --plan <plan dir> --samples "opening summary says approved" [--n 4]

Reads only. Written during the 2026-09-27 DOHA intake work (see HANDOFF.md).
"""
import argparse
import collections
import json
import re
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def shape(reason):
    return re.sub(r"\d+", "#", re.sub(r"'[^']*'", "'..'", reason))[:100]


def top(title, counter, n=12):
    print(f"\n== {title}")
    for key, count in counter.most_common(n):
        print(f"{count:6}  {key}")


def summary(plan, recheck):
    if plan:
        top("Plan exceptions by reason", collections.Counter(shape(r["reason"]) for r in rows(plan / "exceptions.jsonl")))
    if not recheck:
        return
    top("Re-check: appeal and outcome unsettled", collections.Counter(
        f'{r["field"]}: {shape(r["reason"])}' for r in rows(recheck / "unsettled.jsonl") if r["field"] != "topics"))
    kinds, examples = collections.Counter(), collections.defaultdict(list)
    for r in rows(recheck / "disagreements.jsonl"):
        if r["field"] != "topics":
            continue
        lib, rule = set(filter(None, r["library_value"].split(","))), set(r["rule_value"].split(","))
        rel = "rule adds" if rule > lib else "rule drops" if rule < lib else "disjoint" if not lib & rule else "overlap"
        basis = re.split(r"[ ']", r["rule_evidence"])[0]
        kinds[(rel, basis)] += 1
        examples[(rel, basis)].append(f'{r["case_key"]}: library {r["library_value"] or "-"} / rule {r["rule_value"]} ({r["rule_evidence"][:70]})')
    top("Topic disagreements: how they differ / what the rule read", kinds)
    for key, _ in kinds.most_common(3):
        print(f"\n-- examples: {key}")
        print("\n".join(examples[key][:5]))
    print("\n== Outcome disagreements")
    for r in rows(recheck / "disagreements.jsonl"):
        if r["field"].startswith("outcome"):
            print(f'{r["case_key"]}: [{r["field"]}] library {r["library_value"]} / rule {r["rule_value"]}  {r["rule_evidence"][:80]}')


def samples(plan, phrase, n):
    heading = re.compile(r"^\s*(Statement of the Case|History of the Case|Procedural History|Findings of Fact)\s*$", re.M | re.I)
    for r in [r for r in rows(plan / "exceptions.jsonl") if phrase in r["reason"]][:n]:
        path = plan / "text" / f'{r["case_key"]}.txt'
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        print("\n" + "=" * 70 + f"\n{r['case_key']}: {r['reason'][:200]}")
        findings = list(re.finditer(r"^\s*Formal Findings\s*$", text, re.M | re.I))
        if findings:
            print("\n######## formal findings\n" + text[findings[-1].start():findings[-1].start() + 900])
        history = heading.search(text)
        print("\n######## opening summary\n" + (text[:history.start()] if history else "(no case-history heading)")[:1500])
        print("\n######## end of decision\n" + text[-700:])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--recheck", type=Path)
    parser.add_argument("--samples")
    parser.add_argument("--n", type=int, default=4)
    args = parser.parse_args()
    if args.samples:
        samples(args.plan, args.samples, args.n)
    else:
        summary(args.plan, args.recheck)
