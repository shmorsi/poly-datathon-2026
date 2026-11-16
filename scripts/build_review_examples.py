#!/usr/bin/env python3
"""Build public, rounded review illustrations from the team's four fictional portfolios."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from order_review import DATASET_END, ReviewRequest, build_review, load_market

EXAMPLES = {
    "robert": ("Robert wants to preserve capital with some growth before he retires in three to five years. See what a 40% NVIDIA target changes.", .15),
    "mateo": ("Mateo wants balanced growth over eight to twelve years and wants to avoid companies that conflict with his values.", .25),
    "amira": ("Amira has fifteen years or more to pursue growth. She welcomes volatility and wants to keep her investments diversified.", .45),
    "canadian": ("This workshop example asks how a 20% U.S. equity allocation would change a Canadian-heavy portfolio.", .25),
}


def public_example(review):
    review["mode"] = "saved"
    review["source"] += " Saved chart values are sampled and rounded to the nearest $100."
    review["fund_mode"] = "public-aggregates"
    review["exposure"] = {"before": None, "after": None}
    sides = [review["before"]]
    if review["after"] is not None:
        sides.append(review["after"])
    keep = {side[field] for side in sides for field in ("peak_date", "trough_date")}
    for side in sides:
        points = side["points"]
        interval = max(5, (len(points) + 256) // 257)
        side["points"] = [[day, round(value / 100) * 100] for i, (day, value) in enumerate(points)
                          if i % interval == 0 or i == len(points) - 1 or day in keep]
        side["sampled"] = True
    for fund in review["funds"]:
        fund["companies"] = []
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "review-demo.json")
    args = parser.parse_args()
    pilots = json.loads((ROOT / "data" / "personas.json").read_text())["pilots"]
    market = load_market(DATASET_END)
    universe = market["universe"]
    if len(universe) < 31:
        raise SystemExit("Use the real organizer data pack to build the public review illustrations.")
    assets = [{"ticker": row.ticker, "name": row.name, "asset_class": row.asset_class}
              for row in universe.itertuples(index=False)]
    examples = []
    for key, (description, limit) in EXAMPLES.items():
        pilot = pilots[key]
        order = pilot.get("request")
        body = ReviewRequest(
            portfolio=pilot["portfolio"], amount=pilot["amount"], drawdown_limit=limit,
            capacity=pilot["profile"]["capacity"], values_screen=key == "mateo",
            crypto_limit=.10 if key == "amira" else None,
            order={k: v for k, v in order.items() if k != "op"} if order else None,
        )
        review = public_example(build_review(body, market=market))
        examples.append({"id": key, "name": pilot["name"], "description": description,
                         "limits_note": "Portfolio values, orders and limits are illustrative assumptions for this case.",
                         "input": body.model_dump(), "result": review})
    args.out.write_text(json.dumps({"assets": assets, "examples": examples},
                                   separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {len(examples)} illustrations, {args.out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
