import argparse
import requests
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

SLACK_WEBHOOK_URL = ""
VALID_GENDERS        = {"MALE", "FEMALE", "UNISEX"}
VALID_AGE            = {"ADULT", "JUNIOR", "CHILD"}
VALID_STATUS         = {"True", "False"}
VALID_SELLING_STATUS = {"DISPLAY", "NOT_DISPLAY"}
VALID_SEASONS        = {"SPRING", "SUMMER", "AUTUMN", "WINTER"}
REQUIRED_COLUMNS     = [
                        "item_id",
                        "site_id",
                        "created",
                        "updated",
                        "brand",
                        "category1",
                        "category2",
                        "gender",
                        "status",
                        "selling_status",
                        "season",
                        "image_url",
                        "product_name"
                        ]


@dataclass(frozen=True)
class Failure:
    item_id: str
    reason: str
    detail: str = ""


def clean_text(value: object) -> str:
    """Normalize empty/NaN-like values into clean strings."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_seasons(value: str) -> List[str]:
    """Parse season strings such as '["SUMMER","AUTUMN"]' or 'SUMMER'."""
    if not value:
        return []
    seasons = re.findall(r"SPRING|SUMMER|AUTUMN|WINTER", value)
    return seasons


def get_season_from_month(month: int) -> str:
    month_to_season = {
         3: "SPRING",  4: "SPRING", 5: "SPRING",
         6: "SUMMER",  7: "SUMMER", 8: "SUMMER",
         9: "AUTUMN", 10: "AUTUMN",
        11: "WINTER", 12: "WINTER", 1: "WINTER", 2: "WINTER",
    }

    return month_to_season.get(month)

def validate_items(items: pd.DataFrame, site_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return valid item rows and invalid rows with failure reasons."""

    df = items.copy()
    df = df[df["site_id"] == site_id].reset_index(drop=True)

    for col in REQUIRED_COLUMNS:
        df[col] = df[col].map(clean_text)

    failure_rows = []
    valid_mask = pd.Series(True, index=df.index)

    def mark_invalid(mask: pd.Series, reason: str) -> None:
        nonlocal valid_mask
        bad = valid_mask & mask
        for _, row in df[bad].iterrows():
            failure_rows.append({"item_id": row["item_id"], "name": row['product_name'], "reason": reason})
        valid_mask &= ~mask

    for col in ["item_id", "created", "updated", "brand", "category1", "category2", "gender", "season", "image_url"]:
        mark_invalid(df[col].eq(""), f"missing_{col}")

    mark_invalid(~df["gender"].isin(VALID_GENDERS),                "invalid_gender")
    mark_invalid(~df["status"].isin(VALID_STATUS),                 "invalid_status")
    mark_invalid(~df["selling_status"].isin(VALID_SELLING_STATUS), "invalid_selling_status")

    valid = df[valid_mask].reset_index(drop=True)
    invalid = pd.DataFrame(failure_rows).drop_duplicates() if failure_rows else pd.DataFrame(columns=["item_id", "name", "reason"])
    return valid, invalid

def filter_outfit_seed(
        valid_table: pd.DataFrame,
        curr_season: str,
        update_dates: List[str]) -> pd.DataFrame:
    """Select seed items for outfit generation."""

    df         = valid_table.copy()
    seed_items = df[(df['season'].contains(curr_season)) &
                    (df['selling_status'] == 'DISPLAY')
                    (df['updated']).isin(update_dates)].reset_index(drop=True)

    return seed_items

def load_guidelines(path: str | Path) -> Dict[str, List[Dict[str, List[str]]]]:
    """Load outfit guidelines from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data

def build_item_index(items: pd.DataFrame) -> Dict[str, int]:
    return {str(item_id): idx for idx, item_id in enumerate(items["item_id"].tolist())}


def guideline_contains_seed(guide: Dict[str, List[str]], seed_category1: str, seed_category2: str) -> bool:
    return seed_category1 in guide and seed_category2 in guide[seed_category1]


def filter_candidates(
        items: pd.DataFrame,
        seed_row: pd.Series,
        target_season: str,
        allowed_category2: Iterable[str],
        exclude_ids: Iterable[str]) -> pd.DataFrame:
    """Filter candidates by season, gender, category, and exclusion list."""
    allowed_category2 = set(allowed_category2)
    exclude_ids = set(map(str, exclude_ids))
    seed_gender = seed_row["gender"]

    def season_match(value: object) -> bool:
        return target_season in parse_seasons(value)

    return items[
        items["season"].map(season_match)
        & items["gender"].isin([seed_gender, "UNISEX"])
        & items["category2"].isin(allowed_category2)
        & ~items["item_id"].astype(str).isin(exclude_ids)
        ].copy()


def score_candidate_set(
    item_ids: Sequence[str],
    item_index: Dict[str, int],
    compatibility: np.ndarray,
) -> float:
    """Average pairwise compatibility score for an outfit candidate."""
    ids = [str(x) for x in item_ids]
    if len(ids) < 2:
        return 0.0

    scores = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            scores.append(float(compatibility[item_index[ids[i]], item_index[ids[j]]]))
    return float(np.mean(scores)) if scores else 0.0


def choose_best_candidate(
    current_ids: Sequence[str],
    candidates: pd.DataFrame,
    item_index: Dict[str, int],
    compatibility: np.ndarray,
) -> Optional[str]:
    """Select the candidate that maximizes average compatibility with current outfit items."""
    if candidates.empty:
        return None

    best_id = None
    best_score = -np.inf
    for item_id in candidates["item_id"].astype(str).tolist():
        score = score_candidate_set([*current_ids, item_id], item_index, compatibility)
        if score > best_score:
            best_score = score
            best_id = item_id
    return best_id

def send_slack_alert(webhook_url: str, message: str) -> None:
    payload = {
        "text": f" Outfit Batch Pipeline Alert\n{message}"
    }

    response = requests.post(webhook_url, json=payload)

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack alert failed: {response.status_code}, {response.text}"
        )

def generate_outfits_for_seed(
        seed_row: pd.Series,
        items: pd.DataFrame,
        guidelines: Dict[str, List[Dict[str, List[str]]]],
        compatibility: np.ndarray,
        item_index: Dict[str, int],
        num_styles: int,
        min_candidates_per_slot: int,
        season: str) -> Tuple[List[Dict[str, object]], List[Failure]]:
    """Generate multiple constrained outfit sets for one seed item."""

    seed_id        = str(seed_row["item_id"])
    seed_category1 = str(seed_row["category1"])
    seed_category2 = str(seed_row["category2"])

    failures: List[Failure]           = []
    results:  List[Dict[str, object]] = []

    if season is None:
        return results, [Failure(seed_id, "invalid_seed_season")]

    candidate_guides = [
        guide for guide in guidelines.get(season, [])
        if guideline_contains_seed(guide, seed_category1, seed_category2)
    ]
    if not candidate_guides:
        return results, [Failure(seed_id, "seed_not_in_guideline", f"season={season}, category={seed_category1}/{seed_category2}")]

    used_by_slot: Dict[str, set[str]] = {}

    for style_no in range(1, num_styles + 1):
        guide        = candidate_guides[(style_no - 1) % len(candidate_guides)]
        outfit_ids   = [seed_id]
        slot_details = []
        failed = False

        # Seed slot is already filled. Fill the remaining category1 slots.
        for slot_category1, allowed_category2 in guide.items():
            if slot_category1 == seed_category1:
                continue

            exclude_ids = set(outfit_ids) | used_by_slot.get(slot_category1, set())
            candidates = filter_candidates(
                items=items,
                seed_row=seed_row,
                target_season=season,
                allowed_category2=allowed_category2,
                exclude_ids=exclude_ids,
            )

            if len(candidates) < min_candidates_per_slot:
                failures.append(
                    Failure(
                        seed_id,
                        "not_enough_candidates",
                        f"style_no={style_no}, slot={slot_category1}, candidates={len(candidates)}",
                    )
                )
                failed = True
                break

            chosen_id = choose_best_candidate(outfit_ids, candidates, item_index, compatibility)
            if chosen_id is None:
                failures.append(Failure(seed_id, "candidate_selection_failed", f"style_no={style_no}, slot={slot_category1}"))
                failed = True
                break

            outfit_ids.append(chosen_id)
            used_by_slot.setdefault(slot_category1, set()).add(chosen_id)
            slot_details.append({"slot": slot_category1, "item_id": chosen_id})

        if failed:
            continue

        score = score_candidate_set(outfit_ids, item_index, compatibility)
        record = {
            "seed_item_id": seed_id,
            "style_no": style_no,
            "season": season,
            "outfit_item_ids": "|".join(outfit_ids),
            "score": round(score, 6),
            "slot_details": json.dumps(slot_details, ensure_ascii=False),
        }
        results.append(record)

    return results, failures

def build_failure_summary(failure_report: pd.DataFrame, max_examples: int = 5) -> str:
    if failure_report.empty:
        return "No failures."

    reason_counts = failure_report["reason"].value_counts()

    lines = ["Outfit Batch Failure", ""]
    lines.append(f"Total failures: {len(failure_report)}")
    lines.append("")
    lines.append("Failure counts by reason:")

    for reason, count in reason_counts.items():
        lines.append(f"- {reason}: {count}")

    lines.append("")
    lines.append(f"Examples (top {max_examples}):")

    for _, row in failure_report.head(max_examples).iterrows():
        lines.append(
            f"- item_id={row['item_id']}, reason={row['reason']}, detail={row.get('detail', '')}"
        )

    return "\n".join(lines)

def run_batch(
        items_csv: str | Path,
        site_id: str,
        month: str,
        guidelines_json: str | Path,
        compatibility_npy: Optional[str | Path],
        out_dir: str | Path,
        update_dates: List[str],
        num_styles: int = 3,
        min_candidates_per_slot: int = 1) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the full batch pipeline and write outputs."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_items = pd.read_csv(items_csv, dtype=str)
    valid_items, invalid_items = validate_items(raw_items, site_id)

    if valid_items.empty:
        send_slack_alert(
            webhook_url=SLACK_WEBHOOK_URL,
            message=f"No valid items remain after metadata validation. SITE_ID={site_id}"
        )

        raise ValueError(
            "No valid items remain after metadata validation."
        )

    current_season = get_season_from_month(month)
    seed_items     = filter_outfit_seed(valid_items, current_season, update_dates)

    guidelines = load_guidelines(guidelines_json)
    compatibility = np.load(compatibility_npy)
    item_index = build_item_index(seed_items)

    recommendation_rows: List[Dict[str, object]] = []
    failures: List[Failure] = []

    for _, seed_row in seed_items.iterrows():
        recs, seed_failures = generate_outfits_for_seed(
            seed_row=seed_row,
            items=valid_items,
            guidelines=guidelines,
            compatibility=compatibility,
            item_index=item_index,
            num_styles=num_styles,
            min_candidates_per_slot=min_candidates_per_slot,
            season=current_season,
        )
        recommendation_rows.extend(recs)
        failures.extend(seed_failures)

    recommendations = pd.DataFrame(recommendation_rows)
    failure_report = pd.DataFrame([f.__dict__ for f in failures]) if failures else pd.DataFrame(columns=["item_id", "reason", "detail"])

    message = build_failure_summary(failure_report)
    send_slack_alert(
        webhook_url=SLACK_WEBHOOK_URL,
        message=message
    )

    if not invalid_items.empty:
        invalid_items = invalid_items.assign(detail="metadata_validation")
        invalid_items = invalid_items.rename(columns={"reason": "reason"})
        if "detail" not in invalid_items.columns:
            invalid_items["detail"] = "metadata_validation"
        failure_report = pd.concat(
            [failure_report, invalid_items[["item_id", "reason", "detail"]]],
            ignore_index=True,
        )

    recommendations.to_csv(out_dir / "recommendations.csv", index=False, encoding="utf-8-sig")
    failure_report.to_csv(out_dir / "failure_report.csv", index=False, encoding="utf-8-sig")
    valid_items.to_csv(out_dir / "validated_items.csv", index=False, encoding="utf-8-sig")

    return recommendations, failure_report, valid_items


def parse_args():
    parser = argparse.ArgumentParser(description="Constraint-aware fashion outfit batch pipeline")
    parser.add_argument("--items_csv",          type=str, default="./item_table.csv",         help="Path to item table CSV")
    parser.add_argument("--sitd_id",            type=str,                                     help="Brand/site identifier")
    parser.add_argument("--guidelines_json",    type=str, default="./outfit_guidelines.json", help="Path to outfit guideline JSON")
    parser.add_argument("--compatibility_npy",  type=str, default=None,                       help="Path to pairwise compatibility .npy matrix")
    parser.add_argument("--out_dir",            type=str, default="./outputs",                help="Output directory")
    parser.add_argument("--num_styles",         type=int, default=3,                          help="Number of outfits to generate per seed item")
    parser.add_argument("--min_items_per_slot", type=int, default=1,                          help="Minimum items required per outfit slot")
    return parser.parse_args()


def main():
    # current time
    current_time  = datetime.now()
    current_month = current_time.strftime('%m')
    update_dates  = [(current_time + timedelta(days=-1 * d)).strftime('%Y-%m-%d') for d in range(7)]  # 7 최근 일주일간 업데이트 된 상품들에 대해서 업데이트

    args = parse_args()

    recommendations, failure_report, valid_items = run_batch(
        items_csv=args.items_csv,
        site_id=args.site_id,
        guidelines_json=args.guidelines_json,
        compatibility_npy=args.compatibility_npy,
        out_dir=args.out_dir,
        num_styles=args.num_styles,
        min_candidates_per_slot=args.min_candidates_per_slot,
        month=current_month,
        update_dates=update_dates
    )

    print("Batch completed")
    print(f"valid_items: {len(valid_items)}")
    print(f"recommendations: {len(recommendations)}")
    print(f"failures: {len(failure_report)}")
    print(f"outputs: {Path(args.out_dir).resolve()}")


if __name__ == "__main__":
    main()