import datetime
import json
import pickle
import random
import time
import folium
import numpy as np
from tqdm import tqdm
from folium.plugins import Fullscreen, TagFilterButton
import polyline
import stravalib.exc
from flask import Flask, render_template, request, url_for, session, redirect, jsonify
from flask_caching import Cache
from stravalib import unithelper, Client
from dotenv import load_dotenv
from uuid import uuid4
import os
import pandas as pd

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key
if os.path.exists("settings2.env"):
    load_dotenv("settings2.env")

FLASK_ENV = os.environ.get("FLASK_ENV", "dev")

# Initialize Strava client
client = Client()

RACES = [
    {'name': '1/2 mile', 'distance': 804.67},
    {'name': '1 mile', 'distance': 1609.34},
    {'name': '2 mile', 'distance': 1609.34*2},
    {'name': '5k', 'distance': 5000},
    {'name': '10k', 'distance': 10000},
    {'name': '15k', 'distance': 15000},
    {'name': '10 mile', 'distance': 1609.34*10},
    {'name': 'half marathon', 'distance': 21097.5},
    {'name': 'marathon', 'distance': 21097.5*2}
]

if 'STRAVA_CLIENT_ID' in os.environ:
    print('Found client id')
if 'STRAVA_CLIENT_SECRET' in os.environ:
    print('Found client secret')


# @app.errorhandler(Exception)
# def handle_all_exceptions(error):
#     print(error)
#     raise
#     # return redirect(url_for('fail'))


@app.route("/fail")
def fail():
    return render_template("fail.html", flask_env=FLASK_ENV, cow_path=get_cow_path())


@app.route("/")
def index():
    try:
        authenticated = refresh()
        if authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html', flask_env=FLASK_ENV, cow_path=get_cow_path())
    except:
        return redirect(url_for('logout'))


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


def refresh():
    if 'token_expires_at' in session:
        if time.time() > session['token_expires_at']:
            if 'refresh_token' not in session:
                return False

            try:
                response = client.exchange_code_for_token(
                    client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
                    client_secret=os.getenv("STRAVA_CLIENT_SECRET"),  # Replace with your Strava client secret
                    code=session['refresh_token']
                )
            except stravalib.exc.AccessUnauthorized:
                print('Could not refresh, not authenticated')
                return False
            except Exception as e:
                print("Unkown error: ", e)
                return False

            # Store access token in the session for the user
            session['access_token'] = response['access_token']
            session['refresh_token'] = response['refresh_token']
            session['token_expires_at'] = response['expires_at']
            return True
        else:
            print('Already authenticted')
            return True
    else:
        return False


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
    if request.method == 'GET':
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
    else:
        return redirect(url_for('index'))


def generate_map(activities, save_path, filter=True):
    print('Generating map')

    # Loop through activities and collect map data
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
    m = folium.Map(location=decoded_coords[0], zoom_start=13)

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

    if filter:
        TagFilterButton(activity_types).add_to(m)

    Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    # Save map to an HTML file or render it in the template
    m.save(save_path)


def get_cow_path():
    cow_folder = os.path.join('static', 'images', 'cow')
    filename = random.choice(os.listdir(cow_folder))
    print(filename)
    return url_for('static', filename=os.path.join('images', 'cow', filename))


def fastest_segment_within_distance(df, races):
    for race in races:
        race['start_idx'] = 0
        race['fastest_time'] = None
        race['max_avg_speed'] = 0

    for end_idx in range(1, len(df)):
        for race in races:
            segment_distance = df['distance'][end_idx] - df['distance'][race['start_idx']]
            if segment_distance >= race['distance']:
                segment_time = df['time'][end_idx] - df['time'][race['start_idx']]
                avg_speed = segment_distance / segment_time

                if avg_speed > race['max_avg_speed']:
                    race['max_avg_speed'] = avg_speed
                    race['fastest_time'] = segment_time

                race['start_idx'] += 1
    return races


def calculate_personal_bests(activities, limit=10):
    types = [
        "time",
        "latlng",
        "altitude",
        "heartrate",
        "temp",
    ]

    all_efforts = []
    races = list(RACES)

    count = 0
    for activity in tqdm(activities, total=limit):
        if count >= limit:
            break
        count += 1
        if activity.type == 'Run':
            best_efforts = {}
            streams = client.get_activity_streams(activity.id, types=types, resolution="medium")
            stream_data = {}
            for key, value in streams.items():
                stream_data[key] = value.data
            df = pd.DataFrame(stream_data)

            races = fastest_segment_within_distance(df, races)
            results = {}
            for race in races:
                results[race['name']] = race['fastest_time']
            all_efforts.append(results)

    best_efforts_df = pd.DataFrame(all_efforts).min()
    list_of_dicts = [{'name': index, 'time': seconds_to_time(value)} for index, value in best_efforts_df.items()]
    return list_of_dicts


def get_race_efforts(activities):
    if len(activities) == 0:
        return []
    races = list(RACES)
    for i, activity in enumerate(activities):
        for j, race in enumerate(races):
            if 'activities' not in race:
                race['activities'] = []
            if -10 < (float(activity.distance) - race['distance']) < 250:
                race['activities'].append(activity)
    for race in races:
        if len(race['activities']) > 0:
            race['activity_best'] = min(race['activities'], key=lambda x: x.elapsed_time)
        else:
            race['activity_best'] = None
    return races


def get_activities(strava_athlete, as_dicts=False, activity_types=None, after_date=None):
    athlete_folder = os.path.join("static", "temp", str(strava_athlete.id))
    activities_path = os.path.join(athlete_folder, 'activities.pkl')
    all_activities = []
    if os.path.exists(activities_path) and file_created_within_60_minutes(activities_path):
        with open(activities_path, 'rb') as file:
            all_activities = pickle.load(file)
    if len(all_activities) == 0:
        # Set a higher per_page limit to fetch more activities per request
        per_page = 100

        # Get the initial set of activities
        activities = list(client.get_activities(limit=per_page, after=after_date))

        # Store activities in a list
        all_activities = list(activities)

        # Retrieve remaining activities using pagination
        while len(activities) == per_page:
            # Fetch the next set of activities
            activities = list(client.get_activities(limit=per_page, before=activities[-1].start_date, after=after_date))
            all_activities.extend(list(activities))
        with open(activities_path, 'wb') as file:
            pickle.dump(all_activities, file)

    if as_dicts:
        activities_dicts = []
        for activity in all_activities:
            if activity_types is None or activity.type in activity_types:
                activities_dicts.append({
                    'name': activity.name,
                    'distance': float(round(unithelper.miles(activity.distance), 2)),
                    'type': activity.type,
                    'time': seconds_to_time(activity.moving_time.seconds)
                })
        return activities_dicts
    else:
        return all_activities


def get_gear(activities):
    gear_ids = set()
    for activity in activities:
        if activity.gear_id:
            gear_ids.add(activity.gear_id)
    gear = []
    for gear_id in gear_ids:
        gear_item = client.get_gear(gear_id)
        distance = None
        if gear_item.distance:
            distance = unithelper.miles(gear_item.distance)
        gear.append({'name': gear_item.name, 'distance': distance})
    return gear


def get_trends(activities, activity_types='all'):
    activity_list = []
    activities.reverse()
    for i, activity in enumerate(activities):
        if activity.average_heartrate and (activity_types=='all' or activity.type in activity_types):
            max_speed = round(float(unithelper.miles_per_hour(activity.max_speed)), 2)
            activity_list.append({'date': activity.start_date_local, 'hr': activity.average_heartrate, 'max_speed': max_speed, 'kudos': activity.kudos_count})
    activities_df = pd.DataFrame(activity_list)
    activities_df['date'] = pd.to_datetime(activities_df['date'])
    activities_df.set_index('date', inplace=True)
    activities_df = activities_df.fillna(np.nan).replace([np.nan], [None])

    df_w = activities_df.resample('D').mean().tail(7).replace([np.nan], [None])
    df_d = activities_df.resample('D').mean().tail(30).replace([np.nan], [None])
    df_6m = activities_df.resample('W').mean().tail(6 * 4).replace([np.nan], [None])  # 6 months, at 4 weeks per month
    df_y = activities_df.resample('M').mean().tail(12).replace([np.nan], [None])  # 12 months

    data = {
        'w': {
            'title': 'Last 7 days',
            'dates': df_w.index.day_name().tolist(),
            'values': {
                'hr': df_w['hr'].tolist(),
                'max_speed': df_w['max_speed'].tolist(),
                'kudos': df_w['kudos'].tolist()
            }
        },
        'm': {
            'title': 'Last 30 days',
            'dates': df_d.index.strftime("%b %d").tolist(),
            'values': {
                'hr': df_d['hr'].tolist(),
                'max_speed': df_d['max_speed'].tolist(),
                'kudos': df_d['kudos'].tolist()
            }
        },
        '6m': {
            'title': 'Last 6 months',
            'dates': df_6m.index.strftime("%b %d %y").tolist(),
            'values': {
                'hr': df_6m['hr'].tolist(),
                'max_speed': df_6m['max_speed'].tolist(),
                'kudos': df_6m['kudos'].tolist()
            }
        },
        'y': {
            'title': 'Last 12 months',
            'dates': df_y.index.strftime("%b %y").tolist(),
            'values': {
                'hr': df_y['hr'].tolist(),
                'max_speed': df_y['max_speed'].tolist(),
                'kudos': df_y['kudos'].tolist()
            }
        }

    }
    return data


def get_stats(activities, athlete):
    # Because only run, bike and swim are supported, we have to calculate other total distances
    hike_count = 0
    hike_distance = 0.0
    for activity in activities:
        if activity.type == 'Hike':
            hike_count += 1
            hike_distance += float(unithelper.miles(activity.distance))
    stats = {
        'run': {
            'count': athlete.stats.all_run_totals.count,
            'distance': unithelper.miles(athlete.stats.all_run_totals.distance)
        },
        'bike': {
            'count': athlete.stats.all_ride_totals.count,
            'distance': unithelper.miles(athlete.stats.all_ride_totals.distance)
        },
        'hike': {
            'count': hike_count,
            'distance': hike_distance
        }
    }
    return stats


def seconds_to_time(seconds):
    if seconds is None:
        return None
    days = int(seconds // (24 * 3600))
    hours = int((seconds % (24 * 3600)) // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    time_string = ""

    if days > 0:
        time_string += f"{days} d "
    if hours > 0:
        time_string += f"{hours} h "
    if minutes > 0:
        time_string += f"{minutes} m "
    if seconds > 0 or time_string == "":
        time_string += f"{seconds} s"

    return time_string.strip()


def file_created_within_60_minutes(file_path):
    # Get the creation time of the file
    creation_time = os.path.getctime(file_path)

    # Calculate the difference from the current time
    current_time = time.time()
    age_seconds = current_time - creation_time

    # Check if the file was created over 60 minutes ago
    return age_seconds < 60 * 60  # 60 minutes * 60 seconds


@app.route("/activities_page")
def activities_page():
    authenticated = refresh()
    if not authenticated:
        return redirect(url_for('index'))
    # Use the access token to fetch user data from Strava
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()
    activities = get_activities(strava_athlete)
    return render_template('activities.html', cow_path=get_cow_path(), flask_env=FLASK_ENV, activities=activities)


@app.route("/metrics/<activity_id>")
def metrics(activity_id):
    authenticated = refresh()
    if not authenticated:
        return redirect(url_for('index'))
    # Use the access token to fetch user data from Strava
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()
    activity = client.get_activity(activity_id)
    types = [
        "time",
        "latlng",
        "altitude",
        "heartrate",
        "temp",
    ]
    streams = client.get_activity_streams(activity.id, types=types, resolution="medium")
    relative_path = os.path.join('temp', str(strava_athlete.id), f'{activity_id}.html')
    save_path = os.path.join('static', relative_path)
    heatmap_path = url_for("static", filename=relative_path)
    generate_map([activity], save_path=save_path, filter=False)

    # Extracting time and heart rate data
    time_data = streams['time'].data
    heart_rate_values = streams['heartrate'].data

    # Prepare data for JavaScript
    heart_rate_json = json.dumps({
        'time': time_data,
        'heart_rate': heart_rate_values
    })

    return render_template('metrics.html', cow_path=get_cow_path(), flask_env=FLASK_ENV, hr_data=heart_rate_json, heatmap_path=heatmap_path)


@app.route("/get_data", methods=['POST'])
def get_data():
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()
    activities = get_activities(strava_athlete)
    data = get_trends(activities)
    return jsonify({'data': json.dumps(data)})


@app.route("/dashboard")
def dashboard():
    authenticated = refresh()
    if not authenticated:
        return redirect(url_for('index'))
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()
    athlete_folder = os.path.join("static", "temp", str(strava_athlete.id))
    os.makedirs(athlete_folder, exist_ok=True)
    activities = get_activities(strava_athlete)
    # best_efforts = calculate_personal_bests(activities)
    cow_path = get_cow_path()
    best_efforts = get_race_efforts(activities)
    clubs = client.get_athlete_clubs()
    gear = get_gear(activities)
    # trends = get_trends(activities)
    stats = get_stats(activities, strava_athlete)

    text_path = os.path.join(athlete_folder, 'num.txt')

    num = -1
    if os.path.exists(text_path):
        with open(text_path, 'r') as file:
            try:
                num = int(file.read())
            except:
                print('There was a problem reading the number')
    relative_path = os.path.join('temp', str(strava_athlete.id), 'heatmap.html')
    save_path = os.path.join('static', relative_path)
    if num < len(activities):
        with open(text_path, 'w') as file:
            file.write(str(len(activities)))
        generate_map(activities, save_path)
    heatmap_path = url_for("static", filename=relative_path)
    return render_template('dashboard.html', cow_path=cow_path, flask_env=FLASK_ENV, athlete=strava_athlete,
                           best_efforts=best_efforts, clubs=clubs, gear=gear, stats=stats, heatmap_path=heatmap_path,
                           units=unithelper)


@app.route("/support")
def support():
    cow_path = get_cow_path()
    return render_template('support.html', cow_path=cow_path, flask_env=FLASK_ENV)


@app.route("/game")
def game():
    authenticated = refresh()
    if not authenticated:
        return redirect(url_for('index'))
    one_month_ago = datetime.datetime.today() - datetime.timedelta(days=31)
    activities = get_activities(as_dicts=True, activity_types=['Run'], after_date=one_month_ago)
    activities = sorted(activities, key=lambda x: x['distance'])
    return render_template('game.html', activities=activities)


if __name__ == "__main__":
    # Use the PORT environment variable provided by Heroku
    port = int(os.environ.get('PORT', 5001))

    # Run the app
    app.run(host='0.0.0.0', port=port, debug=True)
