import io
import json
import logging
import os
from collections import Counter
from uuid import uuid4

import seaborn as sns
import stravalib.exc
from dotenv import load_dotenv
from flask import jsonify, redirect, render_template, request, session, url_for

from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from stravalib import unithelper

import app.utils as utils
from app.auth import authenticate
from app import RACES, app, client
from app.data import get_activities, get_all_best_efforts, get_user, get_stream_data_for_activity, get_best_efforts_for_activity, get_splits_for_activity
from app.graph import get_trends

logger = logging.getLogger("moovmetrics")

# cache = Cache(app, config={'CACHE_TYPE': 'simple'})

app.secret_key = 'your_secret_key_here'
if os.path.exists("settings2.env"):
    load_dotenv("settings2.env")

# If FLASK_ENV is not set, default to dev
FLASK_ENV = os.environ.get("FLASK_ENV", "dev")


# A dictinoary for storing the state of background running tasks 
#    Main use is with the personal bests which may take like 30 mins
RUNNING = {}

@app.errorhandler(Exception)
def handle_all_exceptions(error):
    print(error)
    return redirect(url_for('fail'))


@app.route("/fail")
def fail():
    return render_template("fail.html", flask_env=FLASK_ENV, cow_path=utils.get_cow_path())


@app.route("/")
def index():
    try:
        authenticated = authenticate()
        if authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html', flask_env=FLASK_ENV, cow_path=utils.get_cow_path())
    # TODO explicit except
    except stravalib.exc.AccessUnauthorized:
        return redirect(url_for('logout'))
    except Exception as e:
        logger.error(str(e))
        return redirect(url_for("fail"))
        


@app.route("/strava-login")
def strava_login():
    """ Login the current user using the strava callback service
    """
    # Create a unique state for each user session
    session['state'] = str(uuid4())

    # Redirect user to Strava authorization URL
    redirect_uri = url_for('strava_callback', _external=True)
    url = client.authorization_url(
        client_id=os.getenv("STRAVA_CLIENT_ID"),
        redirect_uri=redirect_uri,
        state=session['state'],
        approval_prompt='auto'
    )

    # Debugging statements
    logger.info(f'Here is the redirect: {redirect_uri}')
    logger.info(f"Here is the url: {url}")
    return redirect(url)


# def refresh(client, session):
#     """ Refreshes the current strava token

#     Args:
#         None

#     Returns:
#         bool
    
#     The token_expires_at time is stored in the session and
#     if the current time is past then do a refresh using the
#     client.exchange_code_for_token
#     """
#     if 'token_expires_at' in session:
#         if time.time() > session['token_expires_at']:
#             if 'refresh_token' not in session:
#                 return False
#             try:
#                 response = client.exchange_code_for_token(
#                     client_id=os.getenv("STRAVA_CLIENT_ID"),  # Replace with your Strava client ID
#                     client_secret=os.getenv("STRAVA_CLIENT_SECRET"),  # Replace with your Strava client secret
#                     code=session['refresh_token']
#                 )
#             except stravalib.exc.AccessUnauthorized:
#                 # The user will need to reauthenticate
#                 logger.error('Could not refresh, not authenticated')
#                 return False
#             except Exception as e:
#                 logger.error(f"Unkown error: {e}")
#                 print("Unkown error: ", e)
#                 return False

#             # Store access token in the session for the user
#             session['access_token'] = response['access_token']
#             session['refresh_token'] = response['refresh_token']
#             session['token_expires_at'] = response['expires_at']
#             return True
#         else:
#             print('Already authenticted')
#             return True
#     else:
#         return False


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
        client.access_token = session['access_token']
        strava_athlete = client.get_athlete()
        session['user_id'] = strava_athlete.id
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('index'))


# def generate_map(activities, save_path, filter=True):
#     print('Generating map')

#     # Loop through activities and collect map data
#     routes = []
#     activity_types = []
#     decoded_coords = [(40, -112),]  # Define initial map position (this will get overwritten)
#     for activity in activities:
#         if activity.map and float(activity.distance) > 0:
#             activity_types.append(activity.type)
#             coords = activity.map.summary_polyline
#             if coords:
#                 # Decode the polyline data to retrieve latitude and longitude
#                 decoded_coords = polyline.decode(coords)
#                 p = folium.PolyLine(
#                     smooth_factor=1,
#                     opacity=0.5,
#                     locations=decoded_coords,
#                     color="#FC4C02",
#                     tooltip=activity.name,
#                     weight=5,
#                     tags=[activity.type]
#                 )
#                 routes.append(p)

#     # Create a base map centered on a location
#     m = folium.Map(location=decoded_coords[0], zoom_start=11)

#     # Customize the map controls for mobile devices
#     mobile_styles = """
#         @media (max-width: 768px) { /* Adjust this breakpoint according to your needs */
#             /* Increase the size of map controls for mobile */
#             .leaflet-control {
#                 font-size: 20px;
#             }

#             /* Make the map expand button more accessible on mobile */
#             .leaflet-control-expand-full {
#                 width: 40px;
#                 height: 40px;
#                 line-height: 40px;
#                 font-size: 24px;
#             }
#         }
#     """

#     m.get_root().html.add_child(folium.Element(f"<style>{mobile_styles}</style>"))

#     for route in routes:
#         m.add_child(route)

#     if filter:
#         TagFilterButton(activity_types).add_to(m)

#     Fullscreen(
#         position="topright",
#         title="Expand me",
#         title_cancel="Exit me",
#         force_separate_button=True,
#     ).add_to(m)

#     # Save map to an HTML file or render it in the template
#     m.save(save_path)


# def get_cow_path():
#     cow_folder = os.path.join('app', 'static', 'images', 'cow')
#     filename = random.choice(os.listdir(cow_folder))
#     logger.info(f"Cow picture: {filename}")
#     return url_for('static', filename=os.path.join('images', 'cow', filename))


# def fastest_segment_within_distance(df, all_races):
#     for race in all_races:
#         race['start_idx'] = 0
#         race['fastest_time'] = None
#         race['max_avg_speed'] = 0

#     for end_idx in range(1, len(df)):
#         for race in all_races:
#             segment_distance = df['distance'][end_idx] - df['distance'][race['start_idx']]
#             if segment_distance >= race['distance']:
#                 segment_time = df['time'][end_idx] - df['time'][race['start_idx']]
#                 avg_speed = segment_distance / segment_time

#                 if avg_speed > race['max_avg_speed']:
#                     race['max_avg_speed'] = avg_speed
#                     race['fastest_time'] = segment_time

#                 race['start_idx'] += 1
#     return all_races


# def get_all_race_efforts(activities):
#     all_efforts = []
#     for activity in activities:
#         best_efforts = {"activity": activity}
#         if activity.best_efforts is not None:
#             for best_effort in activity.best_efforts:
#                 elapsed_time = best_effort.elapsed_time
#                 distance = best_effort.distance
#                 best_efforts[get_race_name(distance)] = elapsed_time.seconds
#             all_efforts.append(best_efforts)
#     return all_efforts


# def get_all_race_efforts(strava_athlete, activities, batch_size=5):
#     activities = [x for x in activities if x.type == "Run"]
#     athlete_folder = os.path.join("app", "static", "temp", str(strava_athlete.id))
#     efforts_path = os.path.join(athlete_folder, 'all_race_efforts.pkl')
#     all_efforts = []
#     if os.path.exists(efforts_path):
#         with open(efforts_path, 'rb') as file:
#             all_efforts = pickle.load(file)

#         new_activities = []
#         for activity in activities:
#             if activity.id not in [x["activity"].id for x in all_efforts]:
#                 new_activities.append(activity)
#         if len(new_activities) == 0:
#             return all_efforts
#         else:
#             activities = new_activities

#     types = [
#         "time",
#         "latlng",
#         "altitude",
#         "heartrate",
#         "temp",
#     ]

#     all_races = []
#     for race in RACES:
#         all_races.append({key: value for key, value in race.items()})

#     for i in tqdm(range(len(activities))):
#         if activities[i].type == 'Run':
#             best_efforts = {}
#             streams = client.get_activity_streams(activities[i].id, types=types, resolution="medium")
#             stream_data = {}
#             for key, value in streams.items():
#                 stream_data[key] = value.data
#             df = pd.DataFrame(stream_data)

#             all_races = fastest_segment_within_distance(df, all_races)
#             results = {"activity": activities[i]}
#             for race in all_races:
#                 results[race['name']] = race['fastest_time']
#             all_efforts.append(results)
#             if i % batch_size == 0 and i > 0:
#                 with open(efforts_path, 'wb') as file:
#                     pickle.dump(all_efforts, file)
#                 time.sleep(30)
#     return all_efforts

# def calculate_personal_bests(strava_athlete, activities):
#     all_efforts = get_all_race_efforts(strava_athlete, activities)
#     all_efforts_df = pd.DataFrame(all_efforts)
#     min_indices = all_efforts_df.drop(columns=["activity"]).idxmin()
#     list_of_dicts = []
#     for col in all_efforts_df.columns:
#         if col != "activity":
#             min_index = min_indices[col]
#             min_activity = all_efforts_df.at[min_index, "activity"]
#             time_seconds = all_efforts_df.at[min_index, col]
#             time_minutes = time_seconds / 60
#             miles = meters2miles(get_race_distance(col))
#             speed = min2minsec(round(time_minutes / miles, 2))
#             list_of_dicts.append({
#                 "name": col.title(), 
#                 "activity_name": min_activity.name, 
#                 "start_date_local": min_activity.start_date_local.strftime("%b %d, %y"),
#                 "frmt_speed": speed,
#                 "frmt_time": seconds_to_time(time_seconds),
#                 "distance": f"{round(miles, 2)} miles"
#             })
#     return list_of_dicts


def get_race_efforts(activities):
    if len(activities) == 0:
        return []
    race_efforts = []
    for race in RACES:
        race_efforts.append({'name': race['name'], 'distance': race['distance']})

    for i, activity in enumerate(activities):
        for j, race_effort in enumerate(race_efforts):
            if 'activities' not in race_effort:
                race_effort['activities'] = []
            if -10 < (float(activity.distance) - race_effort['distance']) < 250:
                if activity.id not in [x.id for x in race_effort['activities']]:
                    race_effort['activities'].append(activity)
    for race_effort in race_efforts:
        if len(race_effort['activities']) > 0:
            race_effort['activity_best'] = min(race_effort['activities'], key=lambda x: x.elapsed_time)
        else:
            race_effort['activity_best'] = None
    for race_effort in race_efforts:
        if race_effort['activity_best'] is not None:
            speed = 60 / float(unithelper.miles_per_hour(race_effort['activity_best'].average_speed))
            race_effort['frmt_speed'] = utils.min2minsec(round(speed, 2))
            race_effort['frmt_time'] = utils.format_time(race_effort['activity_best'].elapsed_time)
    return race_efforts


def format_effort_data(races, race_filter=None):
    data = {}

    for race in races:
        if race_filter is not None and race['name'] != race_filter:
            continue
        activities = sorted(race['activities'], key=lambda x: x.start_date_local)
        data[race['name']] = {
            "labels": [x.start_date_local.strftime("%b %d, %y") for x in activities],
            "values": [x.elapsed_time.seconds for x in activities],
            "tips": [utils.min2minsec(60 / float(unithelper.miles_per_hour(x.average_speed))) for x in activities]
        }
    return data


def format_all_effort_data(all_efforts, race_name, effort_filter):
    labels = []
    values = []
    tips = []
    record = None
    this_race_efforts = [x for x in all_efforts if x.race_name == race_name]
    this_race_efforts = sorted(this_race_efforts, key=lambda x: x.activity.start_date_local)
    for effort in this_race_efforts:
        label = effort.activity.start_date_local.strftime("%b %d, %y")
        time_seconds = effort.elapsed_time
        if time_seconds is not None:
            set_record = False
            if record is None:
                record = time_seconds
                set_record = True
            elif time_seconds < record:
                record = time_seconds
                set_record = True
            
            if (effort_filter == "record" and set_record) or effort_filter == "all":
                time_minutes = time_seconds / 60
                miles = utils.meters2miles(utils.get_race_distance(race_name))
                tip = utils.min2minsec(time_minutes / miles)
                labels.append(label)
                values.append(int(time_seconds))
                tips.append(tip)
    return {race_name: {"labels": labels, "values": values, "tips": tips}}
        

# def meters2miles(meters):
#     return meters / 1609.34


# def get_activities(strava_athlete, as_dicts=False, activity_types=None, after_date=None):
#     athlete_folder = os.path.join("static", "temp", str(strava_athlete.id))
#     activities_path = os.path.join(athlete_folder, 'activities.pkl')
#     all_activities = []
#     if os.path.exists(activities_path) and file_created_within_60_minutes(activities_path):
#         with open(activities_path, 'rb') as file:
#             all_activities = pickle.load(file)
#     if len(all_activities) == 0:
#         # Set a higher per_page limit to fetch more activities per request
#         per_page = 100

#         # Get the initial set of activities
#         activities = list(client.get_activities(limit=per_page, after=after_date))

#         # Store activities in a list
#         all_activities = list(activities)

#         # Retrieve remaining activities using pagination
#         while len(activities) == per_page:
#             # Fetch the next set of activities
#             activities = list(client.get_activities(limit=per_page, before=activities[-1].start_date, after=after_date))
#             all_activities.extend(list(activities))

#         with open(activities_path, 'wb') as file:
#             pickle.dump(all_activities, file)

#     if as_dicts:
#         activities_dicts = []
#         for activity in all_activities:
#             if activity_types is None or activity.type in activity_types:
#                 activities_dicts.append({
#                     'name': activity.name,
#                     'id': activity.id,
#                     'date': activity.start_date_local,
#                     'distance': float(round(unithelper.miles(activity.distance), 2)),
#                     'average_speed': activity.average_speed,
#                     'type': activity.type,
#                     'time': format_time(activity.moving_time),
#                     'elapsed_time': activity.elapsed_time.seconds,
#                     'elevation': float(round(unithelper.feet(activity.total_elevation_gain)))
#                 })
#         return activities_dicts
#     else:
#         return all_activities


# def get_gear(activities):
#     gear_ids = set()
#     for activity in activities:
#         if activity.gear_id:
#             gear_ids.add(activity.gear_id)
#     gear = []
#     for gear_id in gear_ids:
#         gear_item = client.get_gear(gear_id)
#         distance = None
#         if gear_item.distance:
#             distance = unithelper.miles(gear_item.distance)
#         gear.append({'name': gear_item.name, 'distance': distance})
#     return gear


# def calculate_VO2_max(activity):
#     """
#     Calculate VO2 max using Astrand-Ryhming nomogram.
#     """
#     if activity.type == "Run":
#         average_heartrate = activity.average_heartrate
#         average_speed = activity.average_speed

#         VO2_max = 2900 * float(average_speed) / float(average_heartrate)
#         #Astrand-Ryhming nomogram parameters
#         # a = 0.1
#         # b = 0.84

#         # work_rate = float(unithelper.meters_per_second(average_speed)) * 60
#         # VO2_max = ((work_rate) / (a * average_heart_rate - b))  # mL/(kg*min)
#         # VO2_max = float(unithelper.meters_per_second(average_speed)) * 0.192 + 0.058 * average_heart_rate + 7.04
#         return round(VO2_max, 2)
#     else:
#         return None


# def get_trends(activities, activity_types='all'):
#     activity_list = []
#     activities.reverse()
#     for i, activity in enumerate(activities):
#         if activity.average_heartrate and (activity_types[0] =='all' or activity.type.lower() in activity_types):
#             avg_speed = round(float(unithelper.miles_per_hour(activity.average_speed)), 2)
#             vo2_max = calculate_VO2_max(activity)
#             activity_list.append({
#                 'date': activity.start_date_local, 
#                 'hr': activity.average_heartrate, 
#                 'avg_speed': avg_speed, 
#                 'kudos': activity.kudos_count,
#                 'vo2_max': vo2_max,
#                 'pr_count': activity.pr_count,
#                 'distance': round(float(unithelper.miles(activity.distance)), 2)
#             })
#     activities_df = pd.DataFrame(activity_list)
#     activities_df['date'] = pd.to_datetime(activities_df['date'])
#     activities_df.set_index('date', inplace=True)
#     activities_df = activities_df.fillna(np.nan).replace([np.nan], [None])

#     df_w = activities_df.resample('D').mean().round(2).tail(7).replace([np.nan], [None])
#     df_d = activities_df.resample('D').mean().round(2).tail(30).replace([np.nan], [None])
#     df_6m = activities_df.resample('W').mean().round(2).tail(6 * 4).replace([np.nan], [None])  # 6 months, at 4 weeks per month
#     df_y = activities_df.resample('M').mean().round(2).tail(12).replace([np.nan], [None])  # 12 months

#     data = {
#         'units':{
#             'hr': 'bpm',
#             'avg_speed': 'mph',
#             'kudos': 'count'
#         },
#         'w': {
#             'title': 'Last 7 days',
#             'dates': df_w.index.strftime("%b %d").tolist(),
#             'values': {
#                 'hr': df_w['hr'].tolist(),
#                 'avg_speed': df_w['avg_speed'].tolist(),
#                 'kudos': df_w['kudos'].tolist(),
#                 'vo2_max': df_w['vo2_max'].tolist(),
#                 'pr_count': df_w['pr_count'].tolist(),
#                 'distance': df_w['distance'].tolist()
#             }
#         },
#         'm': {
#             'title': 'Last 30 days',
#             'dates': df_d.index.strftime("%b %d").tolist(),
#             'values': {
#                 'hr': df_d['hr'].tolist(),
#                 'avg_speed': df_d['avg_speed'].tolist(),
#                 'kudos': df_d['kudos'].tolist(),
#                 'vo2_max': df_d['vo2_max'].tolist(),
#                 'pr_count': df_d['pr_count'].tolist(),
#                 'distance': df_d['distance'].tolist()
#             }
#         },
#         '6m': {
#             'title': 'Last 6 months',
#             'dates': df_6m.index.strftime("%b %d %y").tolist(),
#             'values': {
#                 'hr': df_6m['hr'].tolist(),
#                 'avg_speed': df_6m['avg_speed'].tolist(),
#                 'kudos': df_6m['kudos'].tolist(),
#                 'vo2_max': df_6m['vo2_max'].tolist(),
#                 'pr_count': df_6m['pr_count'].tolist(),
#                 'distance': df_6m['distance'].tolist()
#             }
#         },
#         'y': {
#             'title': 'Last 12 months',
#             'dates': df_y.index.strftime("%b %y").tolist(),
#             'values': {
#                 'hr': df_y['hr'].tolist(),
#                 'avg_speed': df_y['avg_speed'].tolist(),
#                 'kudos': df_y['kudos'].tolist(),
#                 'vo2_max': df_y['vo2_max'].tolist(),
#                 'pr_count': df_y['pr_count'].tolist(),
#                 'distance': df_y['distance'].tolist()
#             }
#         }

#     }
#     return data


# def get_stats(activities):
#     stats = {}
#     for activity in activities:
#         if activity.distance is not None and activity.distance > 0:
#             if activity.type not in stats.keys():
#                 stats[activity.type] = {'count': 0, 'distance': 0.0}
#             stats[activity.type]['count'] += 1
#             stats[activity.type]['distance'] += float(unithelper.miles(activity.distance))
#     return stats


# def speed_to_time(speed):
#     mph = float(unithelper.miles_per_hour(speed))
#     min_per_mile = 60 / mph
#     return min2minsec(min_per_mile)


# def seconds_to_time(seconds, calc_days=True, show_seconds=True):
#     if seconds is None:
#         return None
#     days = 0
#     if calc_days:
#         days, seconds = divmod(seconds, 86400)
#     hours, seconds = divmod(seconds, 3600)
#     minutes, seconds = divmod(seconds, 60)

#     time_string = ""

#     if days > 0:
#         time_string += f"{int(days)}d "
#     if hours > 0 or days is None:
#         time_string += f"{int(hours)}h "
#     if minutes > 0:
#         time_string += f"{int(minutes)}m "
#     if seconds > 0 or time_string == "" and show_seconds:
#         time_string += f"{int(seconds)}s"

#     return time_string.strip()


# def file_created_within_60_minutes(file_path):
#     # Get the creation time of the file
#     creation_time = os.path.getctime(file_path)

#     # Calculate the difference from the current time
#     current_time = time.time()
#     age_seconds = current_time - creation_time

#     # Check if the file was created over 60 minutes ago
#     return age_seconds < 60 * 60  # 60 minutes * 60 seconds


# def get_race_name(distance):
#     distance = int(distance)
#     for race in RACES:
#         if abs(distance - race['distance']) < 10:
#             return race['name']
#     return f"{distance} meters"

# def get_race_distance(name):
#     for race in RACES:
#         if race["name"] == name:
#             return race["distance"]
#     return None

# def get_sports_bar_graph(df):
#     # Sports bar graph
#     # Your plot creation logic here using Figure
#     fig = Figure(figsize=(5, 3))
#     ax = fig.add_subplot(111)

#     # Assuming activities_df is your DataFrame
#     type_percentage = df['type'].value_counts(normalize=True) * 100

#     # Create a bar plot
#     sns.barplot(x=type_percentage.values, y=type_percentage.index, palette='viridis', ax=ax, joinstyle="bevel")
#     new_patches = []
#     for patch in reversed(ax.patches):
#         # print(bb.xmin, bb.ymin,abs(bb.width), abs(bb.height))
#         bb = patch.get_bbox()
#         rounding_size = 2
#         if (bb.x1 - bb.x0) < 2:
#             rounding_size = (bb.x1 - bb.x0) * 0.9
#         color = patch.get_facecolor()
#         p_bbox = FancyBboxPatch((bb.xmin, bb.ymin),
#                                 abs(bb.width), abs(bb.height),
#                                 boxstyle=f"round,pad=-0.0040,rounding_size={rounding_size}",
#                                 ec="none", fc=color,
#                                 mutation_aspect=0.2
#                                 )
#         patch.remove()
#         new_patches.append(p_bbox)

#     for patch in new_patches:
#         ax.add_patch(patch)

#     # sns.despine(left=True, bottom=True)
#     ax.spines['top'].set_color('black')
#     ax.spines['bottom'].set_color('black')
#     ax.spines['left'].set_color('black')
#     ax.spines['right'].set_color('black')

#     ax.grid(False)
#     # ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right')
#     ax.tick_params(axis=u'both', which=u'both', length=0, colors="white")
#     ax.set(xlabel='', ylabel='')
#     fig.tight_layout()
#     buffer = io.BytesIO()
#     fig.savefig(buffer, format="png")
#     return Image.open(buffer)


# def get_time_graphs(df):
#     df['Month'] = df['date'].dt.strftime('%b')  # Extract month abbreviation

#     # Find the month with the maximum rows
#     months_df = df['Month'].value_counts().rename_axis("Month").to_frame("counts")
#     months_df = months_df.reset_index()
#     months_df["Percentage"] = months_df["counts"] / months_df["counts"].max()

#     # Sort months for plotting
#     months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
#     months_df['Month'] = pd.Categorical(months_df['Month'], categories=months_order, ordered=True)
#     months_df.sort_values(by="Month", inplace=True)
#     months_df = months_df.set_index("Month")

#     fig = Figure(figsize=(8, 12))
#     # Create subplots using add_subplot
#     axes = [fig.add_subplot(4, 3, i + 1) for i in range(12)]


#     # Plot the circular bar charts
#     for ax, month in zip(axes, months_order):
#         if month not in months_df.index:
#             percentage = 0
#         else:
#             percentage = months_df.loc[month, 'Percentage']

#         # Plot circular bar chart
#         ax.pie([percentage, 1 - percentage], radius=1.5, startangle=270, counterclock=False, colors=['blue', 'black'], wedgeprops={'width': 0.5, 'edgecolor': 'black'})

#         # Add the month abbreviation to the center of each chart
#         ax.text(0.5, 0.5, month, transform=ax.transAxes, ha='center', va='center', fontsize=20, fontweight='bold')

#     # Customize the layout and appearance
#     fig.suptitle('Circular Bar Percentage Charts by Month', y=1.05)

#     buffer = io.BytesIO()
#     fig.savefig(buffer, format="png")
#     return Image.open(buffer)

# def insert_text(image, text, position, font_size=20, font_color=(255, 255, 255)):
#     draw = ImageDraw.Draw(image)
#     font = ImageFont.load_default(font_size)
#     draw.text(position, str(text), font=font, fill=font_color)

# def insert_image(background, overlay, position, size=None):
#     if size is not None:
#         overlay = overlay.resize(size)
#     background.paste(overlay, position, overlay)

# def get_year_in_review(athlete, save_folder):
#     # Customize the style
#     sns.set(style='dark', rc={'axes.facecolor': 'black', 'figure.facecolor': 'black', 'grid.color': 'black', 'text.color': 'white'})
#     activities = get_activities(athlete, as_dicts=True)
#     activities_df = pd.DataFrame(activities)
#     year = datetime.datetime.now().year - 1
#     # filter activities to the year
#     activities_df = activities_df[activities_df['date'].dt.year == year]

#     # 1 Summary
#     total_time = seconds_to_time(activities_df['elapsed_time'].sum(), calc_days=False, show_seconds=False)
#     total_distance = round(activities_df['distance'].sum())
#     top_sport = activities_df['type'].value_counts().idxmax()
#     total_elevation = round(activities_df['elevation'].sum())
#     days_active = activities_df['date'].dt.date.nunique()
#     response = requests.get(athlete.profile)
#     profile = Image.open(io.BytesIO(response.content)).convert("RGBA")
#     name = f"{athlete.firstname} {athlete.lastname}"
#     template_1 = Image.open(os.path.join("static", "images", "year_in_review", "year_in_sport.png"))
#     insert_text(template_1, year, (1000, 120), font_size=125)
#     insert_text(template_1, name, (300, 600), font_size=50)
#     insert_text(template_1, "Total Time", (250, 825), font_size=50)
#     insert_text(template_1, total_time, (250, 925), font_size=100)
#     insert_text(template_1, "Total Distance", (250, 1350), font_size=50)
#     insert_text(template_1, f"{total_distance} miles", (250, 1450), font_size=100)
#     insert_text(template_1, "Total Elevation", (250, 1900), font_size=50)
#     insert_text(template_1, f"{total_elevation} feet", (250, 2000), font_size=100)
#     insert_text(template_1, "Days Active", (1050, 1350), font_size=50)
#     insert_text(template_1, days_active, (1050, 1450), font_size=100)
#     insert_text(template_1, "Top Sport", (1050, 825), font_size=50)
#     insert_text(template_1, top_sport, (1050, 925), font_size=100)
#     insert_image(template_1, profile, (300, 400))
#     template_1.save(os.path.join(save_folder, "image_1.png"))

#     # 2 Sports bar graph
#     template_2 = Image.open(os.path.join("static", "images", "year_in_review", "top_sports.png"))
#     bar_graph = get_sports_bar_graph(activities_df)
#     insert_text(template_2, f"Top Sport: {top_sport}", (250, 400), font_size=75)
#     insert_image(template_2, bar_graph, (100, 1410), (1500, 900))
#     template_2.save(os.path.join(save_folder, "image_2.png"))

#     # 3 Total Time
#     time_graphs = get_time_graphs(activities_df)
#     time_graphs.save(os.path.join(save_folder, "image_3.png"))

#     # Circular bar graphs
#     # https://stackoverflow.com/questions/59672712/circular-barplot-in-python-with-percentage-labels
@app.route("/profile_page")
def profile_page():
    authenticated = authenticate()
    if not authenticated:
        return redirect(url_for('index'))
    strava_athlete = get_user()
    activities = get_activities()
    clubs = client.get_athlete_clubs()
    gear = utils.get_gear(activities)
    # trends = get_trends(activities)
    stats = utils.get_stats(activities)
    return render_template('profile.html', cow_path=utils.get_cow_path(), flask_env=FLASK_ENV, athlete=strava_athlete,
                           clubs=clubs, gear=gear, stats=stats)

@app.route("/best_efforts_page")
def best_efforts_page():
    authenticated = authenticate()
    if not authenticated:
        return redirect(url_for('index'))
    strava_athlete = get_user()
    return render_template('best_efforts.html', cow_path=utils.get_cow_path(), flask_env=FLASK_ENV, athlete=strava_athlete, races=list(RACES))

@app.route("/activities_page")
def activities_page():
    authenticated = authenticate()
    if not authenticated:
        return redirect(url_for('index'))
    strava_athlete = get_user()
    activities = get_activities()
    activities_list = []
    for activity in activities:
        if activity.distance > 0:
            elapsed_time = activity.elapsed_time
            pace = utils.speed_to_time(activity.average_speed)
            frmt_details = f"{elapsed_time} - {pace} /mi"
        else:
            frmt_details = ""
        activities_list.append({
            "frmt_details": frmt_details,
            "id": activity.id,
            "date": activity.start_date_local,
            "name": activity.name
        })

    return render_template('activities.html', cow_path=utils.get_cow_path(), flask_env=FLASK_ENV, activities=activities_list, athlete=strava_athlete)

# def format_time(elapsed_time):
#     """Erase the leading zeros and colons"""
#     time_str = str(elapsed_time)
#     # Split the string at colons
#     time_parts = time_str.split(':')
#     new_parts = []
#     strip = True
#     for time_part in time_parts:
#         if strip:
#             time_part = time_part.lstrip('0')
#         if time_part == '':
#             continue
#         elif strip:
#             strip = False
#         new_parts.append(time_part)
    
#     # Join the parts back together with colons
#     cleaned_time = ':'.join(new_parts)
    
#     return cleaned_time


# def min2minsec(total_minutes):
#     # Calculate minutes and seconds
#     minutes = int(total_minutes)
#     seconds = int((total_minutes - minutes) * 60)
    
#     # Format the result as "minutes:seconds"
#     return f"{minutes}:{seconds:02d}"


@app.route("/metrics/<activity_id>")
def metrics(activity_id):
    authenticated = authenticate()
    if not authenticated:
        return redirect(url_for('index'))
    strava_athlete = get_user()
    # Use the access token to fetch user data from Strava
    client.access_token = session['access_token']
    # strava_athlete = client.get_athlete()
    # activity = client.get_activity(activity_id)
    # types = [
    #     "time",
    #     "latlng",
    #     "altitude",
    #     "heartrate",
    #     "temp",
    #     "velocity_smooth"
    # ]
    activity = get_activities([activity_id])[0]
    splits = get_splits_for_activity(activity.strava_id)
    gear = None
    if activity.gear:
        gear = client.get_gear(activity.gear_id)

    # streams = client.get_activity_streams(activity.id, types=types, resolution="medium")
    altitude_stream = get_stream_data_for_activity(activity.strava_id, data_type="altitude")
    heartrate_stream = get_stream_data_for_activity(activity.strava_id, data_type="heartrate")
    velocity_stream = get_stream_data_for_activity(activity.strava_id, data_type="velocity_smooth")

    time_data = [entry.time for entry in heartrate_stream]
    heartrate_data = [entry.value for entry in heartrate_stream]
    elevation_data = [entry.value for entry in altitude_stream]
    pace_data = [entry.value for entry in velocity_stream]

    heatmap_path = None
    if activity.map != '':
        relative_path = os.path.join('temp', str(session["user_id"]), f'{activity.strava_id}.html')
        save_path = os.path.join('app', 'static', relative_path)
        heatmap_path = url_for("static", filename=relative_path)
        utils.generate_map([activity], save_path=save_path, filter=False)

    # Calculate best efforts
    # best_efforts = []
    # for best_effort in activity.best_efforts:
    #     elapsed_time = best_effort.elapsed_time
    #     distance = best_effort.distance
    #     pace = (elapsed_time.total_seconds() / 60) / float(unithelper.miles(distance))
    #     best_efforts.append({
    #         'time': utils.format_time(elapsed_time), 
    #         'distance': utils.get_race_name(distance),
    #         'pace': utils.min2minsec(round(pace, 2))
    #     })
    best_efforts = get_best_efforts_for_activity(activity.strava_id)
    # Format Best Efforts
    best_efforts_formatted = []
    for best_effort in best_efforts:
        elapsed_time = best_effort.elapsed_time
        if elapsed_time:
            distance = best_effort.distance
            pace = (elapsed_time / 60) / float(utils.meters2miles(distance))
            best_efforts_formatted.append({
                'time': utils.format_time(utils.seconds_to_time(elapsed_time)), 
                'distance': utils.get_race_name(distance),
                'pace': utils.min2minsec(round(pace, 2))
            })
    if len(best_efforts_formatted) == 0:
        best_efforts_formatted = None
        
    # Extracting time and heart rate data
    # time_data = streams['time'].data
    # pace_data = streams['velocity_smooth'].data
    # elevation_data = streams['altitude'].data
    # heart_rate_values = streams['heartrate'].data

    # Prepare data for JavaScript
    if not any(heartrate_data):
        heart_rate_json = json.dumps({})
    else:
        heart_rate_json = json.dumps({
            'time': time_data,
            'values': heartrate_data
        })
    
    if not any(pace_data):
        pace_json = json.dumps({})
    else:
        pace_json = json.dumps({
            'time': time_data,
            'values': [float(unithelper.miles_per_hour(x)) for x in pace_data]
        })
    
    if not any(elevation_data):
        elevation_json = json.dumps({})
    else:
        elevation_json = json.dumps({
            'time': time_data,
            'values': [int(unithelper.feet(x)) for x in elevation_data]
        })
    
    if len(splits) == 0:
        splits_json = json.dumps({})
    else:
        splits_json = json.dumps({
            # 'miles': [f"{float(int(x.split_num)-1)} - {round(utils.meters2miles(x.distance) + (int(x.split_num) - 1), 2)}" for x in splits],
            'miles': [f"{utils.get_split_number(x.distance, x.split_num)}" for x in splits],
            'speed': [utils.mps2mph(x.average_speed) for x in splits],
            'tips': [f"{utils.min2minsec(utils.mps2mpm(x.average_speed))} /mi" for x in splits]
        })

    stats = [
        {"name": "Average Speed", "units": "/mi", "value": utils.min2minsec(round(utils.mps2mpm(activity.average_speed), 2))},
        {"name": "Average Heart Rate", "units": "bpm", "value": int(activity.average_heartrate)},
        {"name": "Elevation Gained", "units": "ft", "value": round(utils.meters2feet(activity.total_elevation_gain), 2)},
        {"name": "Max Speed", "units": "/mi", "value": utils.min2minsec(round(utils.mps2mpm(activity.max_speed), 2))},
        {"name": "Max Heart Rate", "units": "bpm", "value": activity.max_heartrate},
        {"name": "Kudos", "units": "", "value": activity.kudos_count}
    ]
    stats = [x for x in stats if x["value"] is not None and x["value"] != "0:00" and x["value"] != 0]
    
    gear_item = None
    if gear:
        gear_item = {
            "name": gear.name, 
            "distance": float(unithelper.miles(gear.distance))
        }
    return render_template('metrics.html', cow_path=utils.get_cow_path(), flask_env=FLASK_ENV, activity=activity, best_efforts=best_efforts_formatted,
                           hr_data=heart_rate_json, pace_data=pace_json, elevation_data=elevation_json,
                           splits_data=splits_json, heatmap_path=heatmap_path, stats=stats, gear_item=gear_item, athlete=strava_athlete)


@app.route("/get_data", methods=['POST'])
def get_data():
    activity_types = request.get_json()["activity_types"]
    client.access_token = session['access_token']
    activities = get_activities()
    data = get_trends(activities, activity_types=activity_types)
    return jsonify({'data': json.dumps(data)})

@app.route("/get_effort_data", methods=['POST'])
def get_effort_data():
    race_name = request.get_json()['race']
    effort_filter = request.get_json()["effort_filter"]
    client.access_token = session['access_token']
    # strava_athlete = client.get_athlete()
    if session["user_id"] in RUNNING.keys():
        status = RUNNING[session["user_id"]]
        if status == "running":
            return jsonify({'data': "still running"})
        else:
            RUNNING[session["user_id"]] = "running"
    else:
        RUNNING[session["user_id"]] = "running"
    success = False
    try:
        logger.info("Getting best efforts")
        activities = get_activities()
        # a_activities = get_advanced_activities(activities, strava_athlete)
        activities = [x for x in activities if x.type == "Run"]
        all_best_efforts = get_all_best_efforts(activities=activities)
        data = format_all_effort_data(all_best_efforts, race_name, effort_filter)
        best_efforts = utils.calculate_personal_bests(all_best_efforts)
        success = True
    except Exception as e:
        logger.error(f"Error: {e}")
        success = False
    finally:
        RUNNING[session["user_id"]] = "stopped"
    return jsonify({'data': json.dumps(data), "best_efforts": json.dumps(best_efforts), "success": success})


# @app.route("/year_in_review")
# def year_in_review():
#     authenticated = refresh(client, session)
#     if not authenticated:
#         return redirect(url_for('index'))
#     client.access_token = session['access_token']
#     strava_athlete = client.get_athlete()
#     relative_path = os.path.join('temp', str(strava_athlete.id))
#     save_path = os.path.join('static', relative_path)
#     get_year_in_review(strava_athlete, save_path)
#     images_folder = url_for("static", filename=relative_path)
#     image_names = [os.path.join(images_folder, f"image_{x}.png") for x in range(1, 4)]
#     return render_template('year_in_review.html', cow_path=get_cow_path(), flask_env=FLASK_ENV, athlete=strava_athlete, image_names=image_names)



@app.route("/dashboard")
def dashboard():
    # authenticated = utils.refresh(client, session)
    # if not authenticated:
    #     return redirect(url_for('index'))
    # client.access_token = session['access_token']
    # strava_athlete = client.get_athlete()
    strava_athlete = get_user()
    if not strava_athlete:
        return redirect(url_for("index"))
    athlete_folder = os.path.join("app", "static", "temp", str(strava_athlete.id))
    os.makedirs(athlete_folder, exist_ok=True)
    activities = get_activities()
    # activity_types = list(set([x.type.lower() for x in activities]))
    type_counts = Counter(x.type.lower() for x in activities)
    activity_types = [x for x, _ in type_counts.most_common()]

    # best_efforts = calculate_personal_bests(activities)
    cow_path = utils.get_cow_path()
    # best_efforts = get_race_efforts(activities)
    clubs = client.get_athlete_clubs()
    gear = utils.get_gear(activities)
    # trends = get_trends(activities)
    stats = utils.get_stats(activities)

    text_path = os.path.join(athlete_folder, 'num.txt')

    num = -1
    if os.path.exists(text_path):
        with open(text_path, 'r') as file:
            try:
                num = int(file.read())
            except:
                print('There was a problem reading the number')
    relative_path = os.path.join('temp', str(strava_athlete.id), 'heatmap.html')
    save_path = os.path.join('app', 'static', relative_path)
    if num < len(activities):
        with open(text_path, 'w') as file:
            file.write(str(len(activities)))
        utils.generate_map(activities, save_path)
    heatmap_path = url_for("static", filename=relative_path)
    return render_template('dashboard.html', cow_path=cow_path, flask_env=FLASK_ENV, athlete=strava_athlete,
                           clubs=clubs, gear=gear, stats=stats, heatmap_path=heatmap_path,
                           activity_types=activity_types, units=unithelper, races=list(RACES))


@app.route("/support")
def support():
    cow_path = utils.get_cow_path()
    return render_template('support.html', cow_path=cow_path, flask_env=FLASK_ENV)


if __name__ == "__main__":
    # Use the PORT environment variable provided by Heroku
    port = int(os.environ.get('PORT', 5001))

    # Run the app
    app.run(host='0.0.0.0', port=port, debug=True)
