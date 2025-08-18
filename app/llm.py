import os
import pickle
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import time

from openai import OpenAI
from pydantic import BaseModel


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


class TrainingPlan(BaseModel):
    title: str
    duration_weeks: int
    goal: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    author: Optional[str] = None

    workouts: List[Workout]
    notes: Optional[str] = None


def generate_training_plan(form_data: dict, use_dummy: bool = False) -> TrainingPlan:
    """
    Generate a training plan using OpenAI based on form data.

    Args:
        form_data: Dictionary containing user's form responses
        use_dummy: If True, load the dummy pickle file instead of generating a new plan

    Returns:
        TrainingPlan object with the generated plan
    """
    # TODO Reimplement cache system

    # Try to load from cache if requested
    if use_dummy:
        dummy_file = f"app/cache/dummy_plan.pkl"
        try:
            with open(dummy_file, "rb") as f:
                cached_plan = pickle.load(f)
                print(f"Loaded cached training plan from {dummy_file}")
                time.sleep(3)
                return cached_plan
        except Exception as e:
            print(f"Error loading cached plan: {e}")

    # Generate new plan using OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Format the form data for the prompt
    form_answers = f"""
    Primary fitness goal: {form_data.get("goal", "Not specified")}
    Experience level: {form_data.get("experience", "Not specified")}
    Training days per week: {form_data.get("days", "Not specified")}
    """

    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "Generate a comprehensive training plan based on the user's fitness goals and experience level. Create a structured plan with specific workouts for each day of the week over multiple weeks.",
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

    # # Save the plan to cache
    # try:
    #     os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    #     with open(cache_file, "wb") as f:
    #         pickle.dump(training_plan, f)
    #     print(f"Saved training plan to cache: {cache_file}")
    # except Exception as e:
    #     print(f"Error saving plan to cache: {e}")

    return training_plan


def serialize_training_plan(training_plan: TrainingPlan) -> dict:
    """
    Serialize a TrainingPlan to a dictionary with date objects converted to ISO strings.
    """
    data = training_plan.dict()

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
