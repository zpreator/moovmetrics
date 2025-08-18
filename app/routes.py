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
from app.data import get_activities, get_user
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
            return redirect(url_for("dashboard"))
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
    return redirect(url_for("mainapp"))


# --- BEGIN: Dashboard and API endpoints for one-page app ---


# Main app page with questionnaire
@app.route("/mainapp", methods=["GET"])
def mainapp():
    return render_template("mainapp.html")


# Handle questionnaire submission (placeholder)
@app.route("/recommendation", methods=["POST"])
def recommendation():
    try:
        # Get form data
        form_data = {
            "goal": request.form.get("goal"),
            "experience": request.form.get("experience"),
            "days": request.form.get("days"),
        }

        # Check if we should use cached plan (for testing)
        use_dummy = os.getenv("USE_DUMMY", "false").lower() == "true"
        print(f"Using dummy plan: {use_dummy}")

        # Generate training plan using LLM
        training_plan = generate_training_plan(form_data, use_dummy=use_dummy)

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

        return render_template("mainapp.html", success=True, plan=training_plan)

    except Exception as e:
        print(f"Error generating training plan: {e}")
        return render_template("mainapp.html", error=str(e))


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
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("index"))


# --- BEGIN: Dashboard and API endpoints for one-page app ---


@app.route("/dashboard")
def dashboard():
    strava_athlete = get_user()
    if not strava_athlete:
        return redirect(url_for("index"))
    return render_template(
        "dashboard.html",
        cow_path=utils.get_cow_path(),
        flask_env=FLASK_ENV,
        athlete=strava_athlete,
        races=list(RACES),
    )


def get_cached_activities(user_id):
    if not hasattr(g, "activities"):
        g.activities = get_activities(user_id)
    return g.activities


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
    activities = get_cached_activities(athlete.id)
    top_images = get_cached_top_images(athlete.id, activities)
    return jsonify({"urls": top_images})


@app.route("/get_profile_data")
def get_profile_data():
    athlete = get_user()
    activities = get_cached_activities(athlete.id)
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
    activities = get_cached_activities(athlete.id)
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
    activities = get_cached_activities(strava_athlete.id)
    data = get_trends(activities, activity_types=activity_types)
    return jsonify({"data": json.dumps(data)})


@app.route("/get_activity_types")
def get_activity_types():
    strava_athlete = get_user()
    activities = get_cached_activities(strava_athlete.id)

    activity_types = list(set([x.type.lower() for x in activities]))
    type_counts = Counter(x.type.lower() for x in activities)
    activity_types = [x for x, _ in type_counts.most_common()]
    return jsonify({"activity_types": activity_types})


@app.route("/get_heatmap")
def get_heatmap():
    strava_athlete = get_user()
    athlete_folder = os.path.join("app", "static", "temp", str(strava_athlete.id))
    os.makedirs(athlete_folder, exist_ok=True)
    activities = get_cached_activities(strava_athlete.id)
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
