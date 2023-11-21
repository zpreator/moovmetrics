from flask import Flask, render_template, request, url_for, jsonify, session, redirect
from stravalib import Client
from dotenv import load_dotenv
from uuid import uuid4
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key
if os.getenv("STRAVA_CLIENT_ID") is None:
    load_dotenv("settings.env")
# Initialize Strava client
client = Client()


@app.route("/")
def index():
    if 'access_token' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route("/strava-login")
def strava_login():
    # Create a unique state for each user session
    session['state'] = str(uuid4())

    # Redirect user to Strava authorization URL
    url = client.authorization_url(
        client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
        redirect_uri=url_for('strava_callback', _external=True),
        state=session['state'],
        approval_prompt='auto'
    )
    return redirect(url)


@app.route("/strava-callback")
def strava_callback():
    # Validate state to prevent CSRF attacks
    if request.args.get('state') != session.get('state'):
        return "Invalid state. Possible CSRF attack."

    code = request.args.get('code')
    access_token = client.exchange_code_for_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),  # Replace with your Strava client secret
        code=code
    )

    # Store access token in the session for the user
    session['access_token'] = access_token['access_token']

    return redirect(url_for('dashboard'))


@app.route("/dashboard")
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('index'))

    # Use the access token to fetch user data from Strava
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()

    return render_template('dashboard.html', athlete=strava_athlete)


if __name__ == "__main__":
    # Use the PORT environment variable provided by Heroku
    port = int(os.environ.get('PORT', 5000))

    # Run the app
    app.run(host='0.0.0.0', port=port)

#
# app = Flask(__name__)
# # app.config.from_envvar("APP_SETTINGS")
# # app.config.from_envvar("settings.cfg")
# app.config['SECRET_KEY'] = 'the random string'
# load_dotenv('settings.env')
#
# # Initialize Strava client
# client = Client()
#
# @app.route("/")
# def login():
#     url = client.authorization_url(
#         client_id=os.getenv("STRAVA_CLIENT_ID"),
#         redirect_uri=url_for(".logged_in", _external=True),
#         approval_prompt="auto",
#     )
#     return render_template("index.html", authorize_url=url)
#
#
# @app.route("/strava-oauth")
# def logged_in():
#     error = request.args.get("error")
#     state = request.args.get("state")
#     if error:
#         return render_template("login_error.html", error=error)
#     else:
#         code = request.args.get("code")
#         access_token = client.exchange_code_for_token(
#             client_id=os.getenv("STRAVA_CLIENT_ID"),
#             client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
#             code=code,
#         )
#         session['access_token'] = access_token['access_token']
#         strava_athlete = client.get_athlete()
#         return render_template(
#             "heatmap.html",
#             athlete_name=strava_athlete.firstname
#         )
#
#
# def get_heatmap_data(activity_count):
#     activities = client.get_activities(limit=activity_count)
#     coordinates = []
#     for activity in activities:
#         if activity.type == 'Run' and activity.map:
#             coords = activity.map.summary_polyline
#             if coords:
#                 decoded_coords = polyline.decode(coords)
#                 coordinates.extend(decoded_coords)
#     return coordinates
#
#
# @app.route('/heatmap/')
# def heatmap():
#     return render_template('heatmap.html')
#
#
# @app.route('/update_heatmap/<int:activity_count>')
# def update_heatmap(activity_count):
#     heatmap_data = get_heatmap_data(activity_count)
#     return jsonify({'coordinates': heatmap_data})
#
#
# if __name__ == "__main__":
#     app.run(debug=True)
