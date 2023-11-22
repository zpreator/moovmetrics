import time
import folium
from folium.plugins import HeatMap, Fullscreen, TagFilterButton
import polyline
import stravalib.exc
from flask import Flask, render_template, request, url_for, session, redirect
from flask_caching import Cache
from stravalib import unithelper, Client
from dotenv import load_dotenv
from uuid import uuid4
import os

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key
if os.path.exists("settings.env"):
    load_dotenv("settings.env")

FLASK_ENV = os.environ.get("FLASK_ENV", "dev")

# Initialize Strava client
client = Client()


if 'STRAVA_CLIENT_ID' in os.environ:
    print('Found client id')
if 'STRAVA_CLIENT_SECRET' in os.environ:
    print('Found client secret')


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
    redirect_uri = url_for('strava_callback', _external=True)
    print(f'Here is the redirect: {redirect_uri}')
    url = client.authorization_url(
        client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
        redirect_uri=redirect_uri,
        state=session['state'],
        approval_prompt='auto'
    )
    print(f"Here is the url: {url}")
    return redirect(url)


@app.route("/refresh")
def refresh():
    if 'state' not in session:
        return redirect(url_for('index'))

    try:
        response = client.exchange_code_for_token(
            client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
            client_secret=os.getenv("STRAVA_CLIENT_SECRET"),  # Replace with your Strava client secret
            code=session['refresh_token']
        )
    except stravalib.exc.AccessUnauthorized:
        print('Could not refresh, not authenticated')
        return redirect(url_for("index"))

    # Store access token in the session for the user
    session['access_token'] = response['access_token']
    session['refresh_token'] = response['refresh_token']
    session['token_expires_at'] = response['expires_at']
    return redirect(url_for("dashboard"))

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
    # Validate state to prevent CSRF attacks
    if request.args.get('state') != session.get('state'):
        return "Invalid state. Possible CSRF attack."

    code = request.args.get('code')
    response = client.exchange_code_for_token(
        client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
        client_secret=os.getenv("STRAVA_CLIENT_SECRET"),  # Replace with your Strava client secret
        code=code
    )

    # Store access token in the session for the user
    session['access_token'] = response['access_token']
    session['refresh_token'] = response['refresh_token']
    session['token_expires_at'] = response['expires_at']
    return redirect(url_for('dashboard'))


def generate_map():
    print('Generating map')

    # Loop through activities and collect map data
    activities = client.get_activities()
    routes = []
    activity_types = ['Run', 'Hike', 'Ride']
    decoded_coords = [(40, -112),]  # Define initial map position (this will get overwritten)
    for activity in activities:
        if activity.type in activity_types and activity.map:
            coords = activity.map.summary_polyline
            if coords:
                # Decode the polyline data to retrieve latitude and longitude
                decoded_coords = polyline.decode(coords)
                p = folium.PolyLine(
                    smooth_factor=1,
                    opacity=0.5,
                    locations=decoded_coords,
                    color="#FC4C02",
                    tooltip=activity.name,
                    weight=5,
                    tags=[activity.type]
                )
                routes.append(p)

    # Create a base map centered on a location
    m = folium.Map(location=decoded_coords[0], zoom_start=12)

    # Customize the map controls for mobile devices
    mobile_styles = """
        @media (max-width: 768px) { /* Adjust this breakpoint according to your needs */
            /* Increase the size of map controls for mobile */
            .leaflet-control {
                font-size: 20px;
            }

            /* Make the map expand button more accessible on mobile */
            .leaflet-control-expand-full {
                width: 40px;
                height: 40px;
                line-height: 40px;
                font-size: 24px;
            }
        }
    """

    m.get_root().html.add_child(folium.Element(f"<style>{mobile_styles}</style>"))

    for route in routes:
        m.add_child(route)

    TagFilterButton(activity_types).add_to(m)

    Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    # Save map to an HTML file or render it in the template
    m.save(f'static/{session["state"]}/heatmap.html')


@app.route("/dashboard")
@cache.cached(timeout=60)  # Cache the heatmap for 60 seconds
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('index'))
    try:
        # Use the access token to fetch user data from Strava
        client.access_token = session['access_token']
        strava_athlete = client.get_athlete()
        if 'token_expires_at' in session and time.time() > session['token_expires_at']:
            print('Refreshing session')
            redirect(url_for("refresh"))
    except stravalib.exc.AccessUnauthorized:
        return redirect(url_for('logout'))
    os.makedirs(os.path.join("static", str(session['state'])), exist_ok=True)
    activities = client.get_activities()
    hike_count = 0
    hike_distance = 0.0
    for activity in activities:
        if activity.type == 'Hike':
            hike_count += 1
            hike_distance += float(unithelper.miles(activity.distance))
    stats = {
        'run': {
            'count': strava_athlete.stats.all_run_totals.count,
            'distance': unithelper.miles(strava_athlete.stats.all_run_totals.distance)
        },
        'bike': {
            'count': strava_athlete.stats.all_ride_totals.count,
            'distance': unithelper.miles(strava_athlete.stats.all_ride_totals.distance)
        },
        'hike': {
            'count': hike_count,
            'distance': hike_distance
        }
    }
    generate_map()
    return render_template('dashboard.html', athlete=strava_athlete, stats=stats, state=session['state'], flask_env=FLASK_ENV)


if __name__ == "__main__":
    # Use the PORT environment variable provided by Heroku
    port = int(os.environ.get('PORT', 5001))

    # Run the app
    app.run(host='0.0.0.0', port=port, debug=True)
