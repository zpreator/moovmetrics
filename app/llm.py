import logging
import os
import pickle
from datetime import date
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger("moovmetrics")


class Workout(BaseModel):
    week: int
    day_of_week: str  # "Monday", "Tuesday", etc.
    workout_date: Optional[date] = None

    workout_type: str  # "Easy Run", "Intervals", "Long Run", "Cross Training", "Rest"
    distance_km: Optional[float] = None
    duration_minutes: Optional[int] = None
    pace: Optional[str] = None

    event_title: Optional[str] = None
    event_description: Optional[str] = None
    recurrence: Optional[str] = None
    notes: Optional[str] = None


class WeekSummary(BaseModel):
    number: int
    theme: str  # e.g., "Base Building", "Peak Week", "Taper"
    total_distance_km: float
    workout_types: List[str]  # List of workout types this week
    summary: str  # Textual summary of the week's focus


class TrainingPlan(BaseModel):
    title: str
    duration_weeks: int
    goal: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    author: Optional[str] = None

    workouts: List[Workout]
    weeks: List[WeekSummary]  # Weekly summaries
    notes: Optional[str] = None


def generate_training_plan(
    form_data: dict, strava_context: str | None, use_dummy: bool = False
) -> TrainingPlan:
    """
    Generate a training plan using OpenAI based on form data.

    Args:
        form_data: Dictionary containing user's form responses
        use_dummy: If True, load the dummy pickle file instead of generating a new plan

    Returns:
        TrainingPlan object with the generated plan
    """
    if use_dummy:
        dummy_file = "app/cache/dummy_plan.pkl"
        try:
            with open(dummy_file, "rb") as f:
                cached_plan = pickle.load(f)
                logger.debug(f"Loaded dummy training plan from {dummy_file}")
                return cached_plan
        except Exception as e:
            logger.warning(f"Could not load dummy plan, generating live: {e}")

    # Generate new plan using OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Prepare the form answers
    form_answers = f"""
    Primary fitness goal: {form_data.get("goal", "Not specified")}
    Experience level (beginner, intermediate, advanced): {form_data.get("experience", "Not specified")}
    Intensity (mild, medium, hot, spicy): {form_data.get("intensity", "Not specified")}
    Start date: {form_data.get("start_date", "Not specified")}
    """

    if strava_context:
        form_answers += f"\n\nHere are some automatically generated Strava stats, use them to inform your training plan: {strava_context}"

    response = client.beta.chat.completions.parse(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": """Generate a training plan based on the user's fitness goals and experience level. Create a structured plan with specific workouts for each day of the week over multiple weeks. If you suggest N weeks, ensure the output has N weeks of workouts. Do not be too verbose, keep the notes section 1-2 sentences.

For each week, provide a summary that includes:
1. A theme (e.g., "Base Building", "Peak Week", "Recovery", "Taper")
2. Total distance for the week in kilometers
3. Types of workouts included that week (e.g., "Easy runs, Long run, Tempo")
4. A brief summary of the week's focus or progression

The weekly summaries should show clear progression through the training cycle and help users understand how each week contributes to their goal.""",
            },
            {
                "role": "user",
                "content": f"Use these answers to generate a detailed training plan: {form_answers}",
            },
        ],
        response_format=TrainingPlan,
    )

    training_plan = response.choices[0].message.parsed
    if training_plan is None:
        raise Exception("Failed to generate training plan from OpenAI")

    return training_plan


def serialize_training_plan(training_plan: TrainingPlan) -> dict:
    """
    Serialize a TrainingPlan to a dictionary with date objects converted to ISO strings.
    """
    data = training_plan.model_dump()

    # Convert date objects to ISO strings
    if data.get("start_date"):
        data["start_date"] = data["start_date"].isoformat()
    if data.get("end_date"):
        data["end_date"] = data["end_date"].isoformat()

    # Convert workout dates
    for workout in data.get("workouts", []):
        if workout.get("workout_date"):
            workout["workout_date"] = workout["workout_date"].isoformat()

    return data


def deserialize_training_plan(data: dict) -> TrainingPlan:
    """
    Deserialize a dictionary to a TrainingPlan with ISO strings converted back to date objects.
    """
    # Create a copy to avoid modifying the original
    data_copy = data.copy()

    # Convert ISO strings back to date objects
    if data_copy.get("start_date") and isinstance(data_copy["start_date"], str):
        try:
            data_copy["start_date"] = date.fromisoformat(data_copy["start_date"])
        except (ValueError, TypeError):
            data_copy["start_date"] = None

    if data_copy.get("end_date") and isinstance(data_copy["end_date"], str):
        try:
            data_copy["end_date"] = date.fromisoformat(data_copy["end_date"])
        except (ValueError, TypeError):
            data_copy["end_date"] = None

    # Convert workout dates
    if "workouts" in data_copy:
        workouts_copy = []
        for workout in data_copy["workouts"]:
            workout_copy = workout.copy()
            if workout_copy.get("workout_date") and isinstance(
                workout_copy["workout_date"], str
            ):
                try:
                    workout_copy["workout_date"] = date.fromisoformat(
                        workout_copy["workout_date"]
                    )
                except (ValueError, TypeError):
                    workout_copy["workout_date"] = None
            workouts_copy.append(workout_copy)
        data_copy["workouts"] = workouts_copy

    return TrainingPlan(**data_copy)
