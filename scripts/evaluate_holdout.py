"""Score the preregistered sky-aware noise test from the holdout workflow log.

    gh run view <run id> --log > holdout.log
    python scripts/evaluate_holdout.py holdout.log --run <run id>

Writes data/holdout_result.json and site/data/holdout_result.json. The predictions and the decision rule are
the ones in docs/PREREGISTRATION_SKY_AWARE_NOISE_2026-11-26.md; nothing here is tuned after the fact.
"""
import argparse
import json
import re
from pathlib import Path

from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"Chamaeleon_I": "Chamaeleon I", "Serpens_Main": "Serpens Main", "Corona_Australis": "Corona Australis",
         "NGC_2264": "NGC 2264", "IC_348": "IC 348", "HighLatitude_Control_South": "High-latitude control (south)"}


def parse(log: str):
    fields, cur = {}, None
    for line in log.splitlines():
        m = re.search(r"== data/spherex_holdout/fields/(\w+)/data/calibrated_injection", line)
        if m:
            cur = m.group(1)
            fields.setdefault(cur, {})["primary"] = []
            continue
        m = re.search(r"\{\"field\": \"(\w+)\", \"status\": \"([\w_]+)\", \"checks_passed\": (\d+), \"checks_total\": (\d+)", line)
        if m:
            fields.setdefault(m.group(1), {}).update(status=m.group(2), checks=f"{m.group(3)}/{m.group(4)}")
            continue
        if cur is None:
            continue
        m = re.search(r"flux [\d.]+: (\d+)/20 recovered", line)
        if m:
            fields[cur]["primary"].append(int(m.group(1)))
        elif " structured {" in line:
            d = json.loads(line.split(" structured ", 1)[1])
            fields[cur]["variant"] = d["recovered"]
            fields[cur]["ratio"] = d["sensitivity_ratio"]
        elif " image {" in line:
            fields[cur]["excess"] = json.loads(line.split(" image ", 1)[1])["region_noise_excess"]
        elif line.rstrip().endswith("runner.log"):
            cur = None
    return fields


def evaluate(fields):
    done = {k: v for k, v in fields.items() if v.get("status") == "completed_calibrated_jy_pilot" and "variant" in v}
    rows = [dict(field=k, name=NAMES.get(k, k), excess=v["excess"], primary=v["primary"][2], variant=v["variant"][2],
                 ratio=round(v["ratio"], 4)) for k, v in done.items()]
    rows.sort(key=lambda r: r["excess"])
    ex = [r["excess"] for r in rows]
    p1 = float(spearmanr(ex, [r["primary"] for r in rows]).statistic)
    p4 = float(spearmanr(ex, [r["ratio"] for r in rows]).statistic)
    for r in rows:
        r["p2"] = r["variant"] >= r["primary"] - 2
        r["p3"] = (r["variant"] > r["primary"]) if r["excess"] >= 2 else None
    p2 = all(r["p2"] for r in rows)
    p3 = all(r["p3"] for r in rows if r["p3"] is not None)
    incomplete = [dict(field=k, name=NAMES.get(k, k), status=v.get("status"), checks=v.get("checks"))
                  for k, v in fields.items() if k not in done]
    return dict(rows=rows, incomplete=incomplete,
                P1=dict(rho=round(p1, 3), holds=p1 < 0), P2=dict(holds=p2), P3=dict(holds=p3),
                P4=dict(rho=round(p4, 3), holds=p4 > 0.8), adopted=bool(rows) and p2 and p3)


def r2(x):
    from decimal import Decimal, ROUND_HALF_UP
    return str(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)).replace("-", "−")


def html(res, run):
    yes = lambda b: "holds" if b else "fails"
    rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r2(r['excess'])}</td><td>{r['primary']} of 20</td><td>{r['variant']} of 20</td>"
        f"<td>{r2(r['ratio'])}</td></tr>" for r in res["rows"])
    inc = "; ".join(f"{i['name']} did not complete ({i['checks'].replace('/', ' of ')} field checks passed)" for i in res["incomplete"])
    verdict = ("The decision rule fired: the sky-aware rule is now the reported rule for fields whose sky scatters at least "
               "twice the pipeline noise, and the primary rule is reported beside it.") if res["adopted"] else \
              "The decision rule did not fire: the sky-aware rule stays secondary."
    return (f"<table><thead><tr><th>Field</th><th>Noise excess</th><th>Primary rule, 2 × its limit</th>"
            f"<th>Sky-aware rule, 2 × its limit</th><th>Limit ratio</th></tr></thead><tbody>{rows}</tbody></table>"
            f"<p>P1, recovery falls as the sky gets noisier: Spearman ρ = {r2(res['P1']['rho'])}, {yes(res['P1']['holds'])}. "
            f"P2, the sky-aware rule never loses more than 2: {yes(res['P2']['holds'])}. "
            f"P3, it finds strictly more wherever the excess is 2 or more: {yes(res['P3']['holds'])}. "
            f"P4, its limit ratio tracks the excess: ρ = {r2(res['P4']['rho'])}, {yes(res['P4']['holds'])}.</p>"
            f"<p>{verdict} {inc + '. ' if inc else ''}Each rule is counted at twice its own stated limit, so in a noisy "
            f"field the sky-aware sources are brighter: the gain is an honest limit, not extra sensitivity. "
            f"GitHub Actions run {run}.</p>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--run", default="")
    a = ap.parse_args()
    res = evaluate(parse(Path(a.log).read_text(errors="replace")))
    res["run"] = a.run
    res["preregistration"] = "docs/PREREGISTRATION_SKY_AWARE_NOISE_2026-11-26.md"
    res["html"] = html(res, a.run)
    for out in (ROOT / "data/holdout_result.json", ROOT / "site/data/holdout_result.json"):
        out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "html"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
