import time
import json
import logging
import os
from collections import Counter
from uuid import uuid4

import stravalib.exc
from dotenv import load_dotenv
from flask import g, jsonify, redirect, render_template, request, session, url_for

import app.utils as utils
from app.auth import authenticate
from app import RACES, app, client
from app.data import get_activities, get_user, get_races, get_all_best_efforts
from app.graph import get_trends
from app.llm import (
    generate_training_plan,
    serialize_training_plan,
    deserialize_training_plan,
)
from app.pdf_generator import create_pdf_response

logger = logging.getLogger("moovmetrics")

app.secret_key = "your_secret_key_here"
if os.path.exists("settings.env"):
    load_dotenv("settings.env")

FLASK_ENV = os.environ.get("FLASK_ENV", "dev")

RUNNING = {}


def should_update_activities():
    last_fetch = session.get("last_activities_fetch")
    now = int(time.time())
    # 2 hours = 7200 seconds
    if not last_fetch or now - last_fetch > 7200:
        session["last_activities_fetch"] = now
        print("Fetching new activities from Strava")
        return True
    print("Using cached activities")
    return False


@app.errorhandler(Exception)
def handle_all_exceptions(error):
    print(error)
    return redirect(url_for("fail"))


@app.route("/fail")
def fail():
    return render_template(
        "fail.html", flask_env=FLASK_ENV, cow_path=utils.get_cow_path()
    )


@app.route("/")
def index():
    try:
        authenticated = authenticate()
        if authenticated:
            return redirect(url_for("mainapp"))
        return render_template(
            "index.html", flask_env=FLASK_ENV, cow_path=utils.get_cow_path()
        )
    except stravalib.exc.AccessUnauthorized:
        return redirect(url_for("logout"))
    except Exception as e:
        logger.error(str(e))
        return redirect(url_for("fail"))


# New signup step: handle email POST from index and show signup form


# All login/signup actions go directly to main app
@app.route("/login", methods=["POST"])
def login_email():
    return redirect(url_for("mainapp"))


# Handle signup form submission


@app.route("/signup", methods=["POST"])
def signup():
    return redirect(url_for("mainapp"))


@app.route("/login/strava")
def strava_login():
    """Login the current user using the strava callback service"""
    # Create a unique state for each user session
    session["state"] = str(uuid4())

    # Redirect user to Strava authorization URL
    redirect_uri = url_for("strava_callback", _external=True)
    url = client.authorization_url(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        redirect_uri=redirect_uri,
        state=session["state"],
        approval_prompt="auto",
    )

    # Debugging statements
    logger.info(f"Here is the redirect: {redirect_uri}")
    logger.info(f"Here is the url: {url}")
    return redirect(url)


# Main app page with questionnaire
@app.route("/mainapp", methods=["GET"])
def mainapp():
    # Get success/error messages from session
    success = session.pop("success_plan", False)
    error = session.pop("error_message", None)

    # Get training plan from session if it exists
    plan = None
    if success and "current_training_plan" in session:
        plan = deserialize_training_plan(session["current_training_plan"])

    return render_template(
        "mainapp.html", athlete=get_user(), success=success, plan=plan, error=error
    )


# Handle questionnaire submission (placeholder)
@app.route("/recommendation", methods=["POST"])
def recommendation():
    # Handle reset request
    if request.form.get("reset"):
        # Clear the current plan and success flag
        session.pop("current_training_plan", None)
        session.pop("success_plan", None)
        session.modified = True
        return redirect(url_for("mainapp"))

    try:
        # Check if connected to Strava
        athlete = get_user()
        strava_context = None
        if athlete:
            strava_context = "Strava Stats:\n"
            activities = get_activities(athlete.id)
            stats = utils.get_stats(activities)
            for key, value in stats.items():
                strava_context += f"{key}: Total count: {value['count']}, Total distance: {value['distance']} miles\n"

            races = get_races(None)
            if races:
                # Get race stats
                longest_race = max(races, key=lambda x: x.distance if x.distance else 0)
                fastest_race = min(
                    races,
                    key=lambda x: (
                        x.elapsed_time.total_seconds() / (x.distance)
                        if x.distance and x.elapsed_time
                        else float("inf")
                    ),
                )

                def race_analysis(race) -> str:
                    analysis = ""
                    if race.distance:
                        distance_miles = (
                            race.distance * 0.621371 / 1000
                        )  # Convert m to miles
                        pace_min_per_mile = (
                            race.elapsed_time.total_seconds() / 60 / distance_miles
                        )
                        analysis += f"{race.name} ({distance_miles:.1f} miles), Pace: {pace_min_per_mile:.2f} min/mile, Date: {race.start_date_local.strftime('%Y-%m-%d')}"
                        if race.average_heartrate:
                            analysis += (
                                f", Average HR: {race.average_heartrate:.0f} bpm\n"
                            )
                        else:
                            analysis += "\n"
                    else:
                        return ""
                    return analysis

                # Add detailed race analysis to context
                strava_context += "\nRace Analysis:\n"
                strava_context += f"Longest Race: {race_analysis(longest_race)}"
                strava_context += f"Fastest Race: {race_analysis(fastest_race)}"
                strava_context += f"Most Recent Race: {race_analysis(races[0])}"

                strava_context += "\nRace History (Most Recent):\n"
                for race in races[:5]:  # They should already be sorted by date
                    strava_context += race_analysis(race)

                strava_context += "\nRecent Activities:\n"
                for activity in activities[:10]:
                    strava_context += race_analysis(activity)

        # Get form data
        goal_type = request.form.get("goal_type")

        # Initialize goal description
        goal_description = ""
        if goal_type == "race":
            race_distance = request.form.get("race_distance")
            if race_distance == "custom":
                # Handle custom distance
                distance_value = request.form.get("custom_distance_value")
                distance_unit = request.form.get("custom_distance_unit")
                if not distance_value:
                    raise ValueError("Please enter a distance for your custom race")
                goal_description = (
                    f"Training for a {distance_value} {distance_unit} race"
                )
            else:
                # Map predefined distances to descriptions
                distance_mapping = {
                    "5k": "5K race (3.1 miles)",
                    "10k": "10K race (6.2 miles)",
                    "half": "Half Marathon (13.1 miles)",
                    "marathon": "Marathon (26.2 miles)",
                    "50k": "50K ultramarathon (31 miles)",
                    "50m": "50 Mile ultramarathon",
                    "100k": "100K ultramarathon (62 miles)",
                    "100m": "100 Mile ultramarathon",
                }
                goal_description = f"Training for a {distance_mapping.get(race_distance, race_distance)}"

            # Add race date
            race_date = request.form.get("race_date")
            if race_date:
                goal_description += f" on {race_date}"

        elif goal_type == "injury":
            injury_desc = request.form.get("injury_description")
            goal_description = f"Recovering from injury: {injury_desc}"
        elif goal_type == "improvement":
            goal_description = "Improving running pace and performance"
        elif goal_type == "maintenance":
            goal_description = "Maintaining running fitness"
        elif goal_type == "other":
            goal_description = request.form.get(
                "goal_description", "Custom running goal"
            )

        # Build form data dictionary
        form_data = {
            "sport": "running",  # Hardcoded as we're focusing on running only
            "goal": goal_description,
            "experience": request.form.get("experience"),
            "intensity": request.form.get("intensity"),
            "start_date": request.form.get("start_date"),
        }

        # Check if we should use cached plan (for testing)
        use_dummy = os.getenv("USE_DUMMY", "false").lower() == "true"
        print(f"Using dummy plan: {use_dummy}")

        # Generate training plan using LLM
        training_plan = generate_training_plan(
            form_data, strava_context, use_dummy=use_dummy
        )

        # For now, just print the results
        print("Generated Training Plan:")
        print(f"Title: {training_plan.title}")
        print(f"Duration: {training_plan.duration_weeks} weeks")
        print(f"Goal: {training_plan.goal}")
        print(f"Number of workouts: {len(training_plan.workouts)}")

        for i, workout in enumerate(
            training_plan.workouts[:5]
        ):  # Print first 5 workouts
            print(
                f"Workout {i + 1}: Week {workout.week}, {workout.day_of_week} - {workout.workout_type}"
            )
            if workout.distance_km:
                print(f"  Distance: {workout.distance_km} km")
            if workout.duration_minutes:
                print(f"  Duration: {workout.duration_minutes} minutes")

        if len(training_plan.workouts) > 5:
            print(f"... and {len(training_plan.workouts) - 5} more workouts")

        # Store the training plan in session for PDF generation using proper serialization
        session["current_training_plan"] = serialize_training_plan(training_plan)
        session.modified = True
        session["success_plan"] = True  # Flag to show success message and plan

        return redirect(url_for("mainapp"))

    except Exception as e:
        print(f"Error generating training plan: {e}")
        session["error_message"] = str(e)
        return redirect(url_for("mainapp"))


@app.route("/download-pdf")
def download_pdf():
    """Download the current training plan as a PDF calendar."""
    try:
        # Get the training plan from session
        plan_data = session.get("current_training_plan")
        if not plan_data:
            print("No training plan data found in session")
            return redirect(url_for("mainapp"))

        # Reconstruct the TrainingPlan object using proper deserialization
        print(f"Plan data keys: {plan_data.keys()}")
        training_plan = deserialize_training_plan(plan_data)

        print(f"Successfully reconstructed TrainingPlan: {training_plan.title}")

        # Generate and return PDF
        return create_pdf_response(training_plan)

    except Exception as e:
        print(f"Error generating PDF: {e}")
        import traceback

        traceback.print_exc()
        return redirect(url_for("mainapp"))


@app.route("/logout")
def logout():
    session.clear()
    try:
        client.deauthorize()
    except stravalib.exc.AccessUnauthorized:
        pass
    return redirect(url_for("index"))


@app.route("/strava-callback")
def strava_callback():
    if request.method == "GET":
        if request.args.get("state") != session.get("state"):
            return "Invalid state. Possible CSRF attack."
        code = request.args.get("code")
        response = client.exchange_code_for_token(
            client_id=os.getenv("STRAVA_CLIENT_ID"),
            client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
            code=code,
        )
        session["access_token"] = response["access_token"]
        session["refresh_token"] = response["refresh_token"]
        session["token_expires_at"] = response["expires_at"]
        client.access_token = session["access_token"]
        strava_athlete = client.get_athlete()
        session["user_id"] = strava_athlete.id
        return redirect(url_for("profile"))
    else:
        return redirect(url_for("index"))


@app.route("/profile")
def profile():
    strava_athlete = get_user()
    if not strava_athlete:
        return redirect(url_for("index"))
    return render_template(
        "profile.html",
        cow_path=utils.get_cow_path(),
        flask_env=FLASK_ENV,
        athlete=strava_athlete,
        races=list(RACES),
    )


def get_cached_top_images(user_id, activities):
    cache_key = f"top_images_{user_id}"
    if cache_key in session:
        return session[cache_key]
    top_images = utils.get_top_images(activities)
    session[cache_key] = top_images
    return top_images


@app.route("/get_image_data")
def get_image_data():
    athlete = get_user()
    activities = get_activities(athlete.id, update_db=should_update_activities())
    top_images = get_cached_top_images(athlete.id, activities)
    return jsonify({"urls": top_images})


@app.route("/get_profile_data")
def get_profile_data():
    athlete = get_user()
    activities = get_activities(athlete.id, update_db=should_update_activities())
    stats = utils.get_stats(activities)
    gear = utils.get_gear(activities)
    clubs = client.get_athlete_clubs()
    clubs = [{"name": x.name, "member_count": x.member_count} for x in clubs]
    return jsonify({"stats": stats, "gear": gear, "clubs": clubs})


# Patch: cache gear distances per user in session


def get_cached_gear_distances(user_id, activities):
    cache_key = f"gear_distances_{user_id}"
    if cache_key in session:
        return session[cache_key]
    lines = utils.get_gear_distances(activities)
    session[cache_key] = lines
    return lines


@app.route("/get_gear_data")
def get_gear_data():
    athlete = get_user()
    activities = get_activities(athlete.id, update_db=should_update_activities())
    lines = get_cached_gear_distances(athlete.id, activities)
    data = {"lines": lines}
    return jsonify(data)


@app.route("/get_data", methods=["POST"])
def get_data():
    activity_types = request.get_json()["activity_types"]
    client.access_token = session["access_token"]
    strava_athlete = get_user()
    if not strava_athlete:
        raise Exception("Could not get user")
    activities = get_activities(strava_athlete.id, update_db=should_update_activities())
    data = get_trends(activities, activity_types=activity_types)
    return jsonify({"data": json.dumps(data)})


@app.route("/get_activity_types")
def get_activity_types():
    strava_athlete = get_user()
    activities = get_activities(strava_athlete.id, update_db=should_update_activities())

    activity_types = list(set([x.type.lower() for x in activities]))
    type_counts = Counter(x.type.lower() for x in activities)
    activity_types = [x for x, _ in type_counts.most_common()]
    return jsonify({"activity_types": activity_types})


@app.route("/get_heatmap")
def get_heatmap():
    strava_athlete = get_user()
    athlete_folder = os.path.join("app", "static", "temp", str(strava_athlete.id))
    os.makedirs(athlete_folder, exist_ok=True)
    activities = get_activities(strava_athlete.id, update_db=should_update_activities())
    text_path = os.path.join(athlete_folder, "num.txt")
    num = -1
    if os.path.exists(text_path):
        with open(text_path, "r") as file:
            try:
                num = int(file.read())
            except Exception as e:
                print(f"There was a problem reading the number: {e}")
    relative_path = os.path.join("temp", str(strava_athlete.id), "heatmap.html")
    save_path = os.path.join("app", "static", relative_path)
    if num < len(activities):
        with open(text_path, "w") as file:
            file.write(str(len(activities)))
        utils.generate_map(activities, save_path)
    heatmap_path = url_for("static", filename=relative_path)
    return jsonify({"heatmap_path": heatmap_path})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
