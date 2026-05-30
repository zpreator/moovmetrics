import json
import logging
import os
from typing import List

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger("moovmetrics")


class _WeekEnrichment(BaseModel):
    number: int
    theme: str
    focus: str


class _WorkoutNote(BaseModel):
    week: int
    day: str
    note: str


class _PlanEnrichment(BaseModel):
    title: str
    overview: str
    weeks: List[_WeekEnrichment]
    workouts: List[_WorkoutNote]


def enrich_plan(skeleton: dict) -> dict:
    """
    Call OpenAI to add a title, overview, weekly themes, and per-workout
    descriptions to an algorithmically generated plan skeleton.
    Falls back to the unmodified skeleton on any error.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — skipping plan enrichment")
        return skeleton

    try:
        client = OpenAI(api_key=api_key)

        zones = skeleton["pace_zones"]
        compact_weeks = []
        for week in skeleton["weeks"]:
            active = [
                f"{d['day_name']}: {d['workout_type']} {d['miles']} mi @ {d['pace']}"
                for d in week["days"]
                if d["workout_type"] != "Rest"
            ]
            compact_weeks.append({
                "week": week["number"],
                "phase": week["phase"],
                "total_miles": week["total_miles"],
                "workouts": active,
            })

        prompt = f"""You are an expert running coach writing a personalized training plan.

Runner profile:
- VDOT: {skeleton['vdot']} (Daniels fitness score)
- Current base: {skeleton['base_miles']} mi/week, peak target: {skeleton['peak_miles']} mi/week
- Goal: {skeleton['race_distance']} on {skeleton['race_date']}
- Training paces — Easy: {zones['E']}/mi, Marathon: {zones['M']}/mi, Threshold: {zones['T']}/mi, Interval: {zones['I']}/mi

Plan structure (do NOT change distances or paces):
{json.dumps(compact_weeks, indent=2)}

Return:
- title: concise plan name
- overview: 2-3 sentences describing the overall training approach and periodization
- weeks: for each week, a short theme (3-5 words) and a 1-sentence focus
- workouts: for each non-Rest workout, a 1-sentence description. For quality sessions be specific about structure (e.g. "10-min warm-up + 3×1 mile at T pace + 10-min cool-down"). Keep all notes under 25 words."""

        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, expert running coach."},
                {"role": "user", "content": prompt},
            ],
            response_format=_PlanEnrichment,
        )

        enrichment = response.choices[0].message.parsed
        if not enrichment:
            return skeleton

        week_map = {w.number: w for w in enrichment.weeks}
        note_map = {(w.week, w.day): w.note for w in enrichment.workouts}

        skeleton["title"] = enrichment.title
        skeleton["overview"] = enrichment.overview

        for week in skeleton["weeks"]:
            wn = week["number"]
            if wn in week_map:
                week["theme"] = week_map[wn].theme
                week["focus"] = week_map[wn].focus
            for day in week["days"]:
                key = (wn, day["day_name"])
                if key in note_map and day["workout_type"] != "Rest":
                    day["description"] = note_map[key]

    except Exception as e:
        logger.error(f"Plan enrichment failed: {e}", exc_info=True)

    return skeleton
