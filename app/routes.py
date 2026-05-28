import time
import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
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
    WeekSummary,
)
from app.pdf_generator import create_pdf_response

logger = logging.getLogger("moovmetrics")

if os.path.exists("settings.env"):
    load_dotenv("settings.env")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

FLASK_ENV = os.environ.get("FLASK_ENV", "dev")

RUNNING = {}


def _save_tokens_to_db(strava_id, access_token, refresh_token, expires_at):
    from app.models import User
    user = User.query.filter_by(strava_id=str(strava_id)).first()
    if user:
        user.strava_access_token = access_token
        user.strava_refresh_token = refresh_token
        user.strava_token_expires_at = float(expires_at)
        try:
            from app import db
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving tokens to DB: {e}")
            from app import db
            db.session.rollback()


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
            return redirect(url_for("profile"))
        return render_template(
            "index.html", flask_env=FLASK_ENV, cow_path=utils.get_cow_path(),
            show_particles=True
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


# Analyze Strava data to recommend initial settings
def analyze_strava_activity_patterns(activities):
    if not activities:
        return None

    # Filter to get only runs from the last 20 activities
    recent_runs = [
        activity
        for activity in activities[:20]
        if activity.type and activity.type.lower() == "run"
    ]

    if not recent_runs:
        return None

    # Sort runs by date
    recent_runs.sort(key=lambda x: x.start_date_local, reverse=True)

    # Calculate average runs per week
    if len(recent_runs) >= 2:
        time_diff = recent_runs[0].start_date_local - recent_runs[-1].start_date_local
        weeks = time_diff.days / 7
        runs_per_week = len(recent_runs) / weeks if weeks > 0 else 0
    else:
        runs_per_week = 0

    # Calculate average distance per run (in miles)
    avg_distance = sum(
        run.distance * 0.000621371 for run in recent_runs if run.distance
    ) / len(recent_runs)

    # Determine experience level and training intensity based on patterns
    def get_experience_level(runs_per_week, avg_distance):
        if runs_per_week >= 5 or avg_distance >= 10:
            return "advanced"
        elif runs_per_week >= 3 or avg_distance >= 5:
            return "intermediate"
        else:
            return "beginner"

    def get_training_intensity(runs_per_week):
        if runs_per_week >= 6:
            return "spicy 6-7 days"
        elif runs_per_week >= 3:
            return "hot 3-5 days"
        elif runs_per_week >= 2:
            return "medium 2-3 days"
        else:
            return "mild 1-2 days"

    return {
        "runs_per_week": round(runs_per_week, 1),
        "avg_distance": round(avg_distance, 1),
        "recommended_experience": get_experience_level(runs_per_week, avg_distance),
        "recommended_intensity": get_training_intensity(runs_per_week),
    }


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

    # Get Strava context and recommendations if user is connected
    strava_context = None
    recommendations = None
    athlete = get_user()
    if athlete:
        activities = get_activities(athlete.id)
        if activities:
            # Generate Strava context
            strava_context = "Strava Stats:\n"
            stats = utils.get_stats(activities)
            for key, value in stats.items():
                strava_context += f"{key}: Total count: {value['count']}, Total distance: {value['distance']} miles\n"

            # Get activity pattern recommendations
            recommendations = analyze_strava_activity_patterns(activities)
            if recommendations:
                strava_context += f"\nActivity Patterns:\n"
                strava_context += (
                    f"Average runs per week: {recommendations['runs_per_week']}\n"
                )
                strava_context += f"Average distance per run: {recommendations['avg_distance']} miles\n"

            # Store context for later use in recommendation
            session["strava_context"] = strava_context

    return render_template(
        "mainapp.html",
        athlete=athlete,
        success=success,
        plan=plan,
        error=error,
        recommendations=recommendations,
    )


# Handle questionnaire submission (placeholder)
@app.route("/recommendation", methods=["POST"])
def recommendation():
    top_activities = 10
    # Handle reset request
    if request.form.get("reset"):
        # Clear the current plan and success flag
        session.pop("current_training_plan", None)
        session.pop("success_plan", None)
        session.modified = True
        return redirect(url_for("mainapp"))

    try:
        # Get stored Strava context
        strava_context = session.get("strava_context")
        races = get_races(None)
        activities = get_activities(get_user().id, top_n=top_activities)
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
                        analysis += f", Average HR: {race.average_heartrate:.0f} bpm\n"
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
            for activity in activities[:top_activities]:
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

        # Get intermediate races
        intermediate_races = []
        for key in request.form.keys():
            if key.startswith("intermediate_race_distance_"):
                race_num = key.split("_")[-1]
                race_date = request.form.get(f"intermediate_race_date_{race_num}")
                race_distance = request.form.get(key)
                if race_date and race_distance:
                    intermediate_races.append(
                        {"distance": race_distance, "date": race_date}
                    )

        # Build form data dictionary with non-empty values
        form_data = {
            "sport": "running",  # Hardcoded as we're focusing on running only
            "goal": goal_description,
        }

        # Add optional fields only if they have values
        if experience := request.form.get("experience"):
            form_data["experience"] = experience
        if intensity := request.form.get("intensity"):
            form_data["intensity"] = intensity
        if num_weeks := request.form.get("num_weeks"):
            form_data["num_weeks"] = num_weeks
        if intermediate_races:
            form_data["intermediate_races"] = intermediate_races

        # Check if we should use cached plan (for testing)
        use_dummy = os.getenv("USE_DUMMY", "false").lower() == "true"
        print(f"Using dummy plan: {use_dummy}")

        # Generate training plan using LLM
        training_plan = generate_training_plan(
            form_data, strava_context, use_dummy=use_dummy
        )

        # Generate week summaries if not provided by LLM
        if not hasattr(training_plan, "weeks") or not training_plan.weeks:
            training_plan.weeks = []
            for week_num in range(1, training_plan.duration_weeks + 1):
                # Get workouts for this week
                week_workouts = [
                    w for w in training_plan.workouts if w.week == week_num
                ]

                # Calculate total distance
                total_distance = sum(w.distance_km or 0 for w in week_workouts)

                # Get unique workout types
                workout_types = list(
                    set(w.workout_type for w in week_workouts if w.workout_type)
                )

                # Determine week theme
                if week_num == training_plan.duration_weeks:
                    theme = (
                        "Race Week"
                        if "race" in form_data.get("goal", "").lower()
                        else "Peak Week"
                    )
                elif week_num == training_plan.duration_weeks - 1:
                    theme = (
                        "Taper Week"
                        if "race" in form_data.get("goal", "").lower()
                        else "Pre-Peak Week"
                    )
                elif week_num == 1:
                    theme = "Base Building"
                else:
                    # Look for key workouts to determine theme
                    if any("tempo" in w.workout_type.lower() for w in week_workouts):
                        theme = "Speed Development"
                    elif any("long" in w.workout_type.lower() for w in week_workouts):
                        theme = "Endurance Building"
                    else:
                        theme = "Building Mileage"

                # Create summary based on workouts
                key_workouts = [
                    w
                    for w in week_workouts
                    if w.workout_type.lower() not in ["rest", "easy run"]
                ]
                if key_workouts:
                    summary = f"Focus on {', '.join(w.workout_type for w in key_workouts[:2])}"
                else:
                    summary = "Building base mileage with easy runs"

                week_summary = WeekSummary(
                    number=week_num,
                    theme=theme,
                    total_distance_km=round(total_distance, 1),
                    workout_types=workout_types,
                    summary=summary,
                )
                training_plan.weeks.append(week_summary)

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
        _save_tokens_to_db(strava_athlete.id, response["access_token"], response["refresh_token"], response["expires_at"])
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
        active_page="profile",
    )


@app.route("/dashboard")
def dashboard():
    strava_athlete = get_user()
    if not strava_athlete:
        return redirect(url_for("index"))
    athlete_id = getattr(strava_athlete, "id", None)
    activities = get_activities(athlete_id, update_db=should_update_activities()) if athlete_id else []
    types_raw = [a.type.lower() for a in activities if a and getattr(a, "type", None)]
    type_counts = Counter(types_raw)
    activity_types = [t for t, _ in type_counts.most_common()]
    return render_template(
        "dashboard.html",
        athlete=strava_athlete,
        activity_types=activity_types,
        active_page="dashboard",
    )


@app.route("/tools")
def tools():
    strava_athlete = get_user()
    is_strava = strava_athlete is not None
    return render_template(
        "tools.html",
        athlete=strava_athlete,
        is_strava=is_strava,
        active_page="tools",
    )


_CANONICAL_DISTANCES = [400, 805, 1000, 1609, 3219, 5000, 10000, 15000, 16093, 20000, 21097, 42195]
_CANONICAL_NAMES = {
    400: "400m",
    805: "1/2 Mile",
    1000: "1K",
    1609: "1 Mile",
    3219: "2 Mile",
    5000: "5K",
    10000: "10K",
    15000: "15K",
    16093: "10 Mile",
    20000: "20K",
    21097: "Half Marathon",
    42195: "Marathon",
}
# Distances that match the Reference Distance dropdown in the race predictor
_REF_DISTANCE_KEYS = {1609, 5000, 10000, 21097, 42195}

def _canonical_dist_key(distance):
    return min(_CANONICAL_DISTANCES, key=lambda d: abs(d - distance))


@app.route("/api/best-efforts")
def best_efforts():
    from app.models import BestEffort, Activity
    from app import db
    from app.data import get_pr_efforts_for_activity
    strava_athlete = get_user()
    if not strava_athlete:
        return jsonify({"efforts": []})
    client.access_token = session["access_token"]
    athlete_id = getattr(strava_athlete, "id", None)
    if athlete_id:
        unprocessed = (
            Activity.query.filter_by(user_id=athlete_id, type="Run")
            .filter(Activity.pr_count > 0)
            .filter(~Activity.best_efforts.any())
            .order_by(Activity.start_date_local.desc())
            .limit(10)
            .all()
        )
        for activity in unprocessed:
            get_pr_efforts_for_activity(activity.strava_id)

    all_efforts = (
        db.session.query(BestEffort, Activity.start_date_local)
        .join(Activity, BestEffort.activity_id == Activity.strava_id)
        .filter(Activity.user_id == athlete_id)
        .all()
    ) if athlete_id else []

    # Build best time per canonical distance, restricted to ref-distance dropdown options
    best_by_distance = {}
    for e, act_date in all_efforts:
        if e.elapsed_time is None:
            continue
        dist_key = _canonical_dist_key(e.distance)
        if dist_key not in _REF_DISTANCE_KEYS:
            continue
        if dist_key not in best_by_distance or e.elapsed_time < best_by_distance[dist_key]["seconds"]:
            best_by_distance[dist_key] = {
                "name": _CANONICAL_NAMES[dist_key],
                "distance_m": dist_key,
                "seconds": e.elapsed_time,
                "date": act_date.isoformat() if act_date else None,
            }

    # Filter out pace-inconsistent entries: a shorter distance must have a faster pace
    # than any longer distance (otherwise the data point is from a bad race).
    sorted_efforts = sorted(best_by_distance.items(), reverse=True)  # longest first
    consistent = []
    fastest_pace = float("inf")  # seconds per meter; lower = faster
    for dist_key, effort in sorted_efforts:
        pace = effort["seconds"] / dist_key
        if pace <= fastest_pace:
            fastest_pace = pace
            consistent.append(effort)

    return jsonify({"efforts": list(reversed(consistent))})


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
    try:
        body = request.get_json()
        activity_types = body["activity_types"]

        if "access_token" not in session:
            return jsonify({"error": "No access token in session"}), 401

        client.access_token = session["access_token"]
        strava_athlete = get_user()
        if not strava_athlete:
            return jsonify({"error": "Could not get user"}), 500

        activities = get_activities(strava_athlete.id, update_db=should_update_activities())
        data = get_trends(activities, activity_types=activity_types)
        return jsonify({"data": json.dumps(data)})
    except Exception as e:
        import traceback
        app.logger.error(f"Error in /get_data: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/get_activity_types")
def get_activity_types():
    strava_athlete = get_user()
    if not strava_athlete:
        return jsonify({"activity_types": []})
    activities = get_activities(strava_athlete.id, update_db=should_update_activities())
    type_counts = Counter(a.type.lower() for a in activities if a and getattr(a, "type", None))
    activity_types = [t for t, _ in type_counts.most_common()]
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


def _load_api_user():
    """Validate the API key and return an authenticated (token-refreshed) User, or a JSON error tuple."""
    from app.models import User
    from app import db

    api_key = request.args.get("key") or request.headers.get("X-API-Key")
    expected_key = os.getenv("TRMNL_API_KEY")
    if not expected_key or api_key != expected_key:
        return None, (jsonify({"error": "Unauthorized"}), 401)

    strava_athlete_id = os.getenv("STRAVA_ATHLETE_ID")
    user = (
        User.query.filter_by(strava_id=strava_athlete_id).first()
        if strava_athlete_id
        else User.query.first()
    )

    if not user or not user.strava_access_token:
        return None, (jsonify({"error": "No authenticated user. Log in via the web app first."}), 503)

    if user.strava_token_expires_at and time.time() > user.strava_token_expires_at:
        try:
            response = client.exchange_code_for_token(
                client_id=os.getenv("STRAVA_CLIENT_ID"),
                client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
                code=user.strava_refresh_token,
            )
            user.strava_access_token = response["access_token"]
            user.strava_refresh_token = response["refresh_token"]
            user.strava_token_expires_at = float(response["expires_at"])
            db.session.commit()
        except Exception as e:
            logger.error(f"API token refresh failed: {e}")
            return None, (jsonify({"error": "Token refresh failed"}), 503)

    client.access_token = user.strava_access_token
    return user, None


@app.route("/api/trmnl")
def trmnl():
    from app.models import Activity
    from stravalib import unithelper

    user, err = _load_api_user()
    if err:
        return err
    assert user is not None

    week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    weekly_activities = Activity.query.filter(
        Activity.user_id == int(user.strava_id),
        Activity.start_date_local >= week_ago,
        Activity.type == "Run",
    ).all()
    weekly_miles = round(sum(float(a.distance or 0) for a in weekly_activities) / 1609.34, 1)

    gear_ids = set(a.gear_id for a in Activity.query.filter_by(user_id=int(user.strava_id)).all() if a.gear_id)
    shoes = []
    for gear_id in gear_ids:
        try:
            gear_item = client.get_gear(gear_id)
            if gear_item.frame_type is None and gear_item.distance:
                miles = int(unithelper.miles(gear_item.distance))  # type: ignore[arg-type]
                shoes.append({"name": gear_item.name, "miles": miles})
        except Exception:
            pass
    shoes.sort(key=lambda x: x["miles"], reverse=True)

    return jsonify({"weekly_miles": weekly_miles, "shoes": shoes})


@app.route("/api/weekly")
def weekly_progress():
    from app.models import Activity

    user, err = _load_api_user()
    if err:
        return err
    assert user is not None

    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    # ISO week: Monday=0 … Sunday=6
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    days_remaining = (week_end - today).days + 1  # inclusive of today

    activity_type = os.getenv("WEEKLY_ACTIVITY_TYPE", "Run")
    week_activities = Activity.query.filter(
        Activity.user_id == int(user.strava_id),
        Activity.start_date_local >= datetime.combine(week_start, datetime.min.time()),
        Activity.type == activity_type,
    ).all()
    miles_this_week = round(sum(float(a.distance or 0) for a in week_activities) / 1609.34, 1)

    goal_miles = float(os.getenv("WEEKLY_GOAL_MILES", "30"))
    percent = min(100, round(miles_this_week / goal_miles * 100)) if goal_miles else 0

    return jsonify({
        "miles_this_week": miles_this_week,
        "goal_miles": goal_miles,
        "percent": percent,
        "days_remaining": days_remaining,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "activity_type": activity_type,
    })


@app.route("/api/hr-vo2max")
def hr_vo2max():
    from app.models import Activity
    strava_athlete = get_user()
    if not strava_athlete:
        return jsonify({"activities": []})
    athlete_id = getattr(strava_athlete, "id", None)
    if not athlete_id:
        return jsonify({"activities": []})

    n_activities = int(request.args.get("n_activities", 30))
    hrmax  = float(request.args.get("hrmax",   190))
    hr_rest = float(request.args.get("hr_rest", 60))

    activities = (
        Activity.query
        .filter_by(user_id=athlete_id, type="Run")
        .filter(Activity.average_heartrate.isnot(None))
        .filter(Activity.average_speed.isnot(None))
        .filter(Activity.elapsed_time > timedelta(seconds=1200))
        .order_by(Activity.start_date_local.desc())
        .limit(n_activities)
        .all()
    )

    results = []
    for a in activities:
        try:
            hr         = float(a.average_heartrate)
            speed_mps  = float(a.average_speed)
            v          = speed_mps * 60          # m/s → m/min
            vo2_at_v   = 0.000104 * v * v + 0.182258 * v - 4.60
            pct        = (hr - hr_rest) / (hrmax - hr_rest)
            if pct <= 0:
                continue
            vo2max = vo2_at_v / pct
            if not (20 < vo2max < 90):
                continue
            distance_miles = round(float(a.distance or 0) / 1609.34, 2)
            date_str = a.start_date_local.strftime("%b %d, %Y") if a.start_date_local else ""
            results.append({
                "date":           date_str,
                "distance_miles": distance_miles,
                "avg_hr":         round(hr, 1),
                "vo2max":         round(vo2max, 1),
            })
        except Exception as e:
            logger.warning(f"Skipping activity for HR vo2max: {e}")

    return jsonify({"activities": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
