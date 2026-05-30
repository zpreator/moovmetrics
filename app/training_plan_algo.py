import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional


# ── VDOT Math (Jack Daniels) ───────────────────────────────────────────────

def compute_vdot(distance_m: float, time_seconds: float) -> float:
    """Compute VDOT from a race performance using the Daniels formula."""
    T = time_seconds / 60.0          # minutes
    V = distance_m / T               # m/min
    vo2 = -4.60 + 0.182258 * V + 0.000104 * V ** 2
    pct = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * T)
        + 0.2989558 * math.exp(-0.1932605 * T)
    )
    return round(vo2 / pct, 1)


def _speed_for_intensity(vdot: float, pct: float) -> float:
    """Speed in m/min at a given fraction of VDOT VO2max."""
    target = vdot * pct
    a, b, c = 0.000104, 0.182258, -(4.60 + target)
    return (-b + math.sqrt(b ** 2 - 4 * a * c)) / (2 * a)


def _fmt_pace(speed_mpm: float) -> str:
    """Convert m/min to 'M:SS' pace per mile."""
    secs = 1609.34 / speed_mpm * 60
    return f"{int(secs // 60)}:{int(secs % 60):02d}"


def pace_zones(vdot: float) -> dict:
    """Return named training pace zones as formatted min:sec /mi strings."""
    e_slow = _fmt_pace(_speed_for_intensity(vdot, 0.65))
    e_fast = _fmt_pace(_speed_for_intensity(vdot, 0.74))
    m = _fmt_pace(_speed_for_intensity(vdot, 0.79))
    t = _fmt_pace(_speed_for_intensity(vdot, 0.88))
    i_spd = _speed_for_intensity(vdot, 0.98)
    i = _fmt_pace(i_spd)
    r = _fmt_pace(i_spd * 1.07)
    return {"E": f"{e_fast}–{e_slow}", "M": m, "T": t, "I": i, "R": r}


# ── Strava Analysis ────────────────────────────────────────────────────────

def weekly_avg_miles(runs: list, n_weeks: int = 8) -> float:
    """Average weekly mileage over the last n_weeks from a list of Activity objects."""
    if not runs:
        return 0.0
    cutoff = date.today() - timedelta(weeks=n_weeks)
    recent = [r for r in runs if r.start_date_local and r.start_date_local.date() >= cutoff]
    if not recent:
        total = sum(float(r.distance or 0) for r in runs[:20]) / 1609.34
        return round(total / 4, 1)
    by_week: dict = defaultdict(float)
    for r in recent:
        key = r.start_date_local.date().isocalendar()[:2]
        by_week[key] += float(r.distance or 0) / 1609.34
    return round(sum(by_week.values()) / len(by_week), 1) if by_week else 0.0


def detect_training_days(runs: list) -> int:
    """Estimate typical training days per week from recent runs."""
    if not runs:
        return 4
    cutoff = date.today() - timedelta(weeks=8)
    recent = [r for r in runs if r.start_date_local and r.start_date_local.date() >= cutoff]
    if not recent:
        return 4
    by_week: dict = defaultdict(set)
    for r in recent:
        key = r.start_date_local.date().isocalendar()[:2]
        by_week[key].add(r.start_date_local.weekday())
    avg = sum(len(v) for v in by_week.values()) / len(by_week) if by_week else 4
    return max(3, min(7, round(avg)))


def best_pr_vdot(athlete_id: int) -> Optional[dict]:
    """
    Compute a robust VDOT estimate by taking the median across multiple PR distances.
    Using the median (rather than the max) makes the result resilient to watch-glitch
    PRs or a single distance that happened to be run in unusually good conditions.
    Returns a dict with the median vdot, representative PR info, and per-distance breakdown.
    """
    from app.models import BestEffort, Activity
    from app import db

    efforts = (
        db.session.query(BestEffort, Activity.start_date_local)
        .join(Activity, BestEffort.activity_id == Activity.strava_id)
        .filter(Activity.user_id == athlete_id)
        .all()
    )
    if not efforts:
        return None

    canonical = [5000, 10000, 21097, 42195, 1609, 3219]
    tolerance = 300

    # Best time per canonical distance
    best_by_dist: dict = {}
    for effort, act_date in efforts:
        if effort.elapsed_time is None:
            continue
        for canon in canonical:
            if abs(effort.distance - canon) <= tolerance:
                if canon not in best_by_dist or effort.elapsed_time < best_by_dist[canon]["seconds"]:
                    best_by_dist[canon] = {
                        "distance_m": canon,
                        "seconds": float(effort.elapsed_time),
                        "date": act_date,
                    }
                break

    if not best_by_dist:
        return None

    dist_names = {5000: "5K", 10000: "10K", 21097: "Half Marathon", 42195: "Marathon", 1609: "1 Mile", 3219: "2 Mile"}

    # Compute VDOT for each distance and collect valid ones
    per_dist: list = []
    for canon, e in best_by_dist.items():
        v = compute_vdot(e["distance_m"], e["seconds"])
        if 20 < v < 90:
            per_dist.append({
                "distance_m": canon,
                "label": dist_names.get(canon, f"{canon}m"),
                "vdot": v,
                "seconds": e["seconds"],
                "date": e["date"],
            })

    if not per_dist:
        return None

    # Median VDOT — robust against outliers
    sorted_by_vdot = sorted(per_dist, key=lambda x: x["vdot"])
    n = len(sorted_by_vdot)
    median_entry = sorted_by_vdot[n // 2]
    median_vdot = median_entry["vdot"]

    secs = int(median_entry["seconds"])
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    return {
        "vdot": round(median_vdot, 1),
        "distance": median_entry["label"],
        "distance_m": median_entry["distance_m"],
        "time_str": time_str,
        "date": median_entry["date"].strftime("%b %Y") if median_entry["date"] else None,
        "n_samples": n,
        "all_vdots": [
            {"dist": e["label"], "vdot": round(e["vdot"], 1)}
            for e in sorted_by_vdot
        ],
    }


def avg_hr_vo2max(athlete_id: int) -> Optional[float]:
    """
    Estimate VO2max (mL/kg/min) from heart-rate data using the Daniels aerobic-demand formula.
    Takes the median across recent qualifying runs for robustness.
    """
    from app.models import Activity
    from datetime import timedelta

    activities = (
        Activity.query
        .filter_by(user_id=athlete_id, type="Run")
        .filter(Activity.average_heartrate.isnot(None))
        .filter(Activity.average_speed.isnot(None))
        .filter(Activity.elapsed_time > timedelta(seconds=1200))
        .order_by(Activity.start_date_local.desc())
        .limit(30)
        .all()
    )

    hrmax, hr_rest = 190.0, 60.0
    estimates = []
    for a in activities:
        try:
            hr = float(a.average_heartrate)
            v = float(a.average_speed) * 60.0  # m/s → m/min
            vo2_at_v = 0.000104 * v ** 2 + 0.182258 * v - 4.60
            pct = (hr - hr_rest) / (hrmax - hr_rest)
            if pct <= 0:
                continue
            est = vo2_at_v / pct
            if 20 < est < 90:
                estimates.append(est)
        except Exception:
            pass

    if not estimates:
        return None
    estimates.sort()
    return round(estimates[len(estimates) // 2], 1)


def vdot_to_race_time(vdot: float, distance_m: float) -> int:
    """
    Predict race finish time in seconds for a given VDOT and distance.
    Solves the Daniels formula iteratively (time ↔ intensity% are coupled).
    """
    T = distance_m / 200.0  # rough initial guess in minutes
    for _ in range(30):
        pct = (
            0.8
            + 0.1894393 * math.exp(-0.012778 * T)
            + 0.2989558 * math.exp(-0.1932605 * T)
        )
        target = vdot * pct
        a, b, c = 0.000104, 0.182258, -(4.60 + target)
        V = (-b + math.sqrt(b ** 2 - 4 * a * c)) / (2 * a)
        T_new = distance_m / V
        if abs(T_new - T) < 0.001:
            break
        T = T_new
    return round(T * 60)


def expected_vdot_gain(vdot: float, n_weeks: int, race_distance_m: float) -> float:
    """
    Estimate expected VDOT improvement over a training cycle.

    Calibrated against the Daniels / Pfitzinger literature:
    - Beginners (VDOT < 38):   ~3-4 pts per 12-week standard cycle
    - Recreational (38-48):    ~2-3 pts
    - Intermediate (48-58):    ~1-2 pts
    - Advanced (58+):          ~0.5-1 pt

    Returns the *expected* (50th-percentile) gain in VDOT points.
    Conservative ≈ 30% of this value; Aggressive ≈ 170%.
    """
    if vdot < 38:
        per_cycle = 3.5
    elif vdot < 48:
        per_cycle = 2.5
    elif vdot < 58:
        per_cycle = 1.5
    else:
        per_cycle = 0.8

    # Scale proportionally to plan length (reference = 12 weeks)
    per_cycle *= min(n_weeks, 16) / 12.0

    # Longer races involve more aerobic volume → marginally more adaptation
    if race_distance_m >= 42195:
        per_cycle *= 1.2
    elif race_distance_m >= 21097:
        per_cycle *= 1.1
    elif race_distance_m < 5000:
        per_cycle *= 0.85

    return round(per_cycle, 2)


# ── Plan Skeleton Generation ───────────────────────────────────────────────

# Day-of-week templates by number of training days (Mon=0 … Sun=6)
_WEEK_TEMPLATES = {
    3: ["Rest", "Quality", "Rest", "Medium",  "Rest",  "Rest",   "Long"],
    4: ["Rest", "Quality", "Easy", "Rest",    "Rest",  "Medium", "Long"],
    5: ["Rest", "Quality", "Easy", "Easy",    "Rest",  "Medium", "Long"],
    6: ["Easy", "Quality", "Easy", "Quality", "Rest",  "Medium", "Long"],
    7: ["Easy", "Quality", "Easy", "Quality", "Easy",  "Medium", "Long"],
}

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_QUALITY_TYPE = {
    "Base":  "Threshold Run",
    "Build": "Tempo Run",
    "Peak":  "Interval Run",
    "Taper": "Threshold Run",
}

# Proportional weights for distance allocation
_SLOT_WEIGHTS = {"Long": 3.0, "Medium": 2.0, "Quality": 1.5, "Easy": 1.0, "Rest": 0.0}


def _assign_miles(template: list, total: float) -> list:
    weights = [_SLOT_WEIGHTS.get(s, 0) for s in template]
    total_w = sum(weights)
    if total_w == 0:
        return [0.0] * len(template)
    raw = [total * w / total_w for w in weights]
    rounded = [round(r * 2) / 2 for r in raw]
    # Adjust Long slot to absorb rounding error
    diff = total - sum(rounded)
    long_idx = next((i for i, s in enumerate(template) if s == "Long"), None)
    if long_idx is not None:
        rounded[long_idx] = round((rounded[long_idx] + diff) * 2) / 2
    return rounded


def determine_phase(week: int, total_weeks: int) -> str:
    progress = week / total_weeks
    if total_weeks <= 6:
        cuts = [(0.5, "Base"), (0.75, "Build"), (0.875, "Peak"), (1.0, "Taper")]
    elif total_weeks <= 10:
        cuts = [(0.4, "Base"), (0.70, "Build"), (0.85, "Peak"), (1.0, "Taper")]
    else:
        cuts = [(0.35, "Base"), (0.65, "Build"), (0.85, "Peak"), (1.0, "Taper")]
    for threshold, phase in cuts:
        if progress <= threshold:
            return phase
    return "Taper"


def _mileage_curve(base: float, peak: float, n_weeks: int) -> list:
    """
    3-on / 1-recovery build from base → peak, then 2-3 week taper and race week.
    """
    taper_weeks = 2 if n_weeks <= 8 else 3
    build_weeks = n_weeks - taper_weeks - 1  # -1 for race week

    miles = []
    for i in range(build_weeks):
        if i > 0 and i % 4 == 3:  # every 4th week is a recovery week
            m = miles[-1] * 0.80
        else:
            progress = i / max(build_weeks - 1, 1)
            m = base + (peak - base) * progress
        miles.append(round(m, 1))

    taper_pcts = [0.75, 0.55, 0.35][:taper_weeks]
    for pct in taper_pcts:
        miles.append(round(peak * pct, 1))

    miles.append(round(peak * 0.25, 1))  # race week
    return miles[:n_weeks]


def build_plan_skeleton(
    base_miles: float,
    days_per_week: int,
    vdot: float,
    race_distance_m: float,
    race_date: date,
    goal_time_s: Optional[float] = None,
) -> dict:
    """
    Build a complete training plan skeleton using Daniels VDOT methodology.
    Returns a plain dict; LLM enrichment fills descriptions and themes later.
    """
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_ahead)

    n_weeks = (race_date - start_date).days // 7
    n_weeks = max(4, min(20, n_weeks))

    # If a goal time is provided, average current and target VDOT for training paces
    if goal_time_s and goal_time_s > 0:
        target_vdot = compute_vdot(race_distance_m, goal_time_s)
        plan_vdot = (vdot + target_vdot) / 2
    else:
        plan_vdot = vdot
    plan_vdot = max(25.0, min(85.0, plan_vdot))

    zones = pace_zones(plan_vdot)

    # Peak mileage scales with race distance
    dist_factor = min(
        [5000, 10000, 21097, 42195], key=lambda d: abs(d - race_distance_m)
    )
    factors = {5000: 1.10, 10000: 1.15, 21097: 1.25, 42195: 1.40}
    peak_miles = round(base_miles * factors.get(dist_factor, 1.20), 1)

    curve = _mileage_curve(base_miles, peak_miles, n_weeks)
    template = _WEEK_TEMPLATES.get(days_per_week, _WEEK_TEMPLATES[5])

    i_speed = _speed_for_intensity(plan_vdot, 0.98)
    pace_for_slot = {
        "Easy":   zones["E"],
        "Medium": zones["E"],
        "Long":   zones["E"],
        "Threshold Run":  zones["T"],
        "Tempo Run":      zones["T"],
        "Interval Run":   zones["I"],
        "Race":           "Goal pace",
        "Rest":           None,
    }

    dist_labels = {5000: "5K", 10000: "10K", 21097: "Half Marathon", 42195: "Marathon"}
    race_label = dist_labels.get(
        min(dist_labels, key=lambda d: abs(d - race_distance_m)),
        f"{race_distance_m / 1000:.1f}K",
    )

    weeks = []
    for w_idx, w_miles in enumerate(curve):
        week_num = w_idx + 1
        week_start = start_date + timedelta(weeks=w_idx)
        phase = determine_phase(week_num, n_weeks)
        is_race_week = week_num == n_weeks
        quality_type = "Easy Run" if is_race_week else _QUALITY_TYPE.get(phase, "Tempo Run")
        mile_alloc = _assign_miles(template, w_miles)

        days = []
        for d_idx, (slot, slot_miles) in enumerate(zip(template, mile_alloc)):
            day_date = week_start + timedelta(days=d_idx)
            is_race_day = is_race_week and day_date == race_date

            if slot == "Rest" and not is_race_day:
                days.append({
                    "day_name": _DAYS[d_idx],
                    "date": day_date.isoformat(),
                    "workout_type": "Rest",
                    "miles": 0,
                    "pace": None,
                    "description": "",
                })
            elif is_race_day:
                days.append({
                    "day_name": _DAYS[d_idx],
                    "date": day_date.isoformat(),
                    "workout_type": "Race",
                    "miles": round(race_distance_m / 1609.34, 1),
                    "pace": "Goal pace",
                    "description": f"Race day — {race_label}. Run your best!",
                })
            else:
                if slot == "Long":
                    wtype = "Long Run"
                elif slot == "Medium":
                    wtype = "Medium Long Run" if not is_race_week else "Easy Run"
                elif slot == "Quality":
                    wtype = quality_type
                else:
                    wtype = "Easy Run"

                days.append({
                    "day_name": _DAYS[d_idx],
                    "date": day_date.isoformat(),
                    "workout_type": wtype,
                    "miles": round(slot_miles, 1),
                    "pace": pace_for_slot.get(wtype, zones["E"]),
                    "description": "",
                })

        weeks.append({
            "number": week_num,
            "phase": phase,
            "total_miles": round(w_miles, 1),
            "theme": f"{phase} — Week {week_num}",
            "focus": "",
            "days": days,
        })

    return {
        "title": f"{n_weeks}-Week {race_label} Training Plan",
        "race_distance": race_label,
        "race_date": race_date.isoformat(),
        "start_date": start_date.isoformat(),
        "n_weeks": n_weeks,
        "vdot": round(plan_vdot, 1),
        "pace_zones": zones,
        "base_miles": base_miles,
        "peak_miles": peak_miles,
        "days_per_week": days_per_week,
        "overview": "",
        "weeks": weeks,
    }
