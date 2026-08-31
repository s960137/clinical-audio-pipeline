"""Maximize feasible one-to-one pairs, then minimize total time distance."""

from collections import defaultdict
import math

import numpy as np
from scipy.optimize import linear_sum_assignment

from .tables import timestamp


MATCH_COLUMNS = ["row_id", "subject_id", "visit_id", "recording_id",
                 "time_delta_seconds", "match_status"]


def match_records(visits, recordings, tolerance_seconds=900):
    if not math.isfinite(tolerance_seconds) or not 0 <= tolerance_seconds <= 86400:
        raise ValueError("Tolerance must be finite and between 0 and 86400 seconds")
    visits = visits.to_dict("records")
    recordings = recordings.to_dict("records")
    groups = defaultdict(list)
    sources = defaultdict(list)
    results = []
    for index, row in enumerate(visits):
        result = {k: row[k] for k in ["row_id", "subject_id", "visit_id"]}
        result.update(recording_id="", time_delta_seconds="", match_status="no_candidate")
        results.append(result)
        try:
            time = timestamp(row["recorded_at"])
            groups[(row["subject_id"], time.date())].append((index, time))
        except ValueError:
            result["match_status"] = "invalid_or_date_only_time"
    # A URL must represent one recording. Conflicting ownership is rejected, not guessed.
    if len({r["source_url"] for r in recordings}) != len(recordings):
        raise ValueError("Duplicate source URLs require source-manifest review")
    for row in recordings:
        try:
            time = timestamp(row["recorded_at"])
        except ValueError:
            raise ValueError("Recording manifest requires valid explicit timestamps") from None
        sources[(row["subject_id"], time.date())].append((row, time))

    for key, group in groups.items():
        candidates = sources[key]
        if not candidates:
            continue
        n, m = len(group), len(candidates)
        # One dummy per row allows unmatched rows without stealing valid recordings.
        # This penalty makes cardinality dominate the sum of all feasible distances.
        penalty = (n + 1) * (tolerance_seconds + 1)
        forbidden = penalty * (n + m + 2)
        cost = np.full((n, m + n), penalty, dtype=float)
        for i, (_, left) in enumerate(group):
            for j, (_, right) in enumerate(candidates):
                distance = abs((left - right).total_seconds())
                cost[i, j] = distance if distance <= tolerance_seconds else forbidden
        rows, cols = linear_sum_assignment(cost)
        optimum = cost[rows, cols].sum()
        for i, j in zip(rows, cols):
            result = results[group[i][0]]
            if j >= m:
                result["match_status"] = "no_feasible_one_to_one_match"
                continue
            # Equal-optimum alternatives are retained for review, not released as pairs.
            alternative = cost.copy()
            alternative[i, j] = forbidden
            ar, ac = linear_sum_assignment(alternative)
            ambiguous = abs(alternative[ar, ac].sum() - optimum) < 1e-6
            result.update(recording_id=candidates[j][0]["recording_id"],
                          time_delta_seconds=float(cost[i, j]),
                          match_status="ambiguous_review" if ambiguous else "matched")
    return results
