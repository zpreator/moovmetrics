import time
import os
import random
import logging

from flask import url_for
import stravalib
import pandas as pd
from stravalib import unithelper
import polyline
import folium
from folium.plugins import Fullscreen, TagFilterButton

from itertools import groupby
from app import client, RACES

logger = logging.getLogger("moovmetrics")


def generate_map(activities, save_path, filter=True):
    """ Creates a folium map of the map data from the given activities"""
    print('Generating map')

    # Loop through activities and collect map data
    routes = []
    activity_types = []
    decoded_coords = [(40, -112),]  # Define initial map position (this will get overwritten)
    for activity in activities:
        if activity.map and float(activity.distance) > 0:
            activity_types.append(activity.type)
            coords = activity.map
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
    m = folium.Map(location=decoded_coords[0], zoom_start=11)

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
        TagFilterButton(list(set(activity_types))).add_to(m)

    Fullscreen(
        position="topright",
        title="Expand me",
        title_cancel="Exit me",
        force_separate_button=True,
    ).add_to(m)

    # Save map to an HTML file or render it in the template
    m.save(save_path)

def get_top_images(activities, top_n=4):
    urls = []
    for activity in activities:
        full_activity = client.get_activity(activity.strava_id)
        if full_activity.photos.primary:
            urls.append({"url": full_activity.photos.primary.urls["600"], "id": activity.id})
        if len(urls) == top_n:
            break
    return urls

def get_activity_image(activity_id):
    activity = client.get_activity(activity_id)
    return activity.photos.primary.urls["600"]

def get_cow_path():
    """ Gets a random cow image to show in the header """
    cow_folder = os.path.join('app', 'static', 'images', 'cow')
    filename = random.choice(os.listdir(cow_folder))
    logger.info(f"Cow picture: {filename}")
    return url_for('static', filename=os.path.join('images', 'cow', filename))


def fastest_segment_within_distance(df, all_races):
    """ Calculate the fastest time for each race within the activity.
    
    For example, if the run was 4 miles, calulate the fastest 5k, 1 mile, 1/2 mile
    etc. at any point during the activity
    
    Args:
        df: Pandas dataframe with a distance column and time column
        all_races: dictionary to store the segment information which already
            contains the basic race names and distances

    Returns:
        List[Dict]: [{"fastest_time": fastest_time, "name": 5k, "distance": 5000}, ...]
    """
    for race in all_races:
        race['start_idx'] = 0
        race['fastest_time'] = None
        race['max_avg_speed'] = 0

    for end_idx in range(1, len(df)):
        for race in all_races:
            segment_distance = df['distance'][end_idx] - df['distance'][race['start_idx']]
            if segment_distance >= race['distance']:
                segment_time = df['time'][end_idx] - df['time'][race['start_idx']]
                avg_speed = segment_distance / segment_time

                if avg_speed > race['max_avg_speed']:
                    race['max_avg_speed'] = avg_speed
                    race['fastest_time'] = segment_time

                race['start_idx'] += 1
    return all_races

def mps2mph(value):
    return value * 2.236936
    
def mps2mpm(value):
    """ Meters per second to minutes per mile"""
    if value == 0:
        return 0
    elif value:
        return 26.8224 / value
    else:
        return None

def meters2feet(value):
    return value * 3.2808

def calculate_personal_bests(all_efforts):
    """ Given a list of efforts, get the best efforts for each race name

    Args:
        all_efforts: List[BestEffort] objects from sql query of BestEffort db

    Returns:
        List[dict]: necessary info for displaying personal bests
    """

    # Sort by race distance
    all_efforts.sort(key=lambda x: x.distance)

    # Groupby race distance
    grouped_objects = groupby(all_efforts, key=lambda x: x.distance)

    # Loop through the groups to get the minimum
    personal_bests = []
    for distance, efforts in grouped_objects:
        try:
            # Filter out efforts with no elapsed time
            valid_efforts = [x for x in efforts if x.elapsed_time is not None]
            if valid_efforts:
                # Get the best effort
                best_effort = min(valid_efforts, key=lambda x: x.elapsed_time)

                # Formatting for the final display
                time_seconds = best_effort.elapsed_time
                time_minutes = time_seconds / 60
                miles = meters2miles(distance)
                speed = min2minsec(round(time_minutes / miles, 2))
                personal_bests.append({
                    "name": best_effort.race_name.title(), 
                    "activity_name": best_effort.activity.name,
                    "activity_id": best_effort.activity.id,
                    "start_date_local": best_effort.activity.start_date_local.strftime("%b %d, %y"),
                    "frmt_speed": speed,
                    "frmt_time": seconds_to_time(time_seconds),
                    "distance": f"{round(miles, 2)} miles"
                })
        except Exception as e:
            logger.error(f"Something went wrong in calculate_personal_bests: {e}")
    return personal_bests

def meters2miles(meters):
    return meters / 1609.34

def get_gear(activities):
    gear_ids = set()
    for activity in activities:
        if activity.gear_id:
            gear_ids.add(activity.gear_id)
    gear = []
    for gear_id in gear_ids:
        try:
            gear_item = client.get_gear(gear_id)
            distance = None
            if gear_item.distance:
                distance = unithelper.miles(gear_item.distance)
            gear.append({'name': gear_item.name, 'distance': int(distance)})
        except stravalib.exc.ObjectNotFound:
            pass
    return gear


def calculate_VO2_max(activity):
    """
    Calculate VO2 max using Astrand-Ryhming nomogram.
    """
    if activity.type == "Run":
        average_heartrate = activity.average_heartrate
        average_speed = activity.average_speed

        VO2_max = 2900 * float(average_speed) / float(average_heartrate)
        #Astrand-Ryhming nomogram parameters
        # a = 0.1
        # b = 0.84

        # work_rate = float(unithelper.meters_per_second(average_speed)) * 60
        # VO2_max = ((work_rate) / (a * average_heart_rate - b))  # mL/(kg*min)
        # VO2_max = float(unithelper.meters_per_second(average_speed)) * 0.192 + 0.058 * average_heart_rate + 7.04
        return round(VO2_max, 2)
    else:
        return None
    

def get_stats(activities):
    stats = {}
    for activity in activities:
        if activity.distance is not None and activity.distance > 0:
            if activity.type not in stats.keys():
                stats[activity.type] = {'count': 0, 'distance': 0.0}
            stats[activity.type]['count'] += 1
            stats[activity.type]['distance'] += float(meters2miles(activity.distance))
    for key, value in stats.items():
        stats[key]["distance"] = int(stats[key]["distance"])
    return stats


def speed_to_time(speed):
    mph = float(unithelper.miles_per_hour(speed))
    min_per_mile = 60 / mph
    return min2minsec(min_per_mile)

def get_split_number(distance, split_number):
    if abs(1610.4 - distance) > 5:
        return round(distance / 1610.4, 2)
    else:
        return split_number

def seconds_to_time(seconds, calc_days=True, show_seconds=True):
    if seconds is None:
        return None
    days = 0
    if calc_days:
        days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    time_string = ""

    if days > 0:
        time_string += f"{int(days)}d "
    if hours > 0 or days is None:
        time_string += f"{int(hours)}h "
    if minutes > 0:
        time_string += f"{int(minutes)}m "
    if seconds > 0 or time_string == "" and show_seconds:
        time_string += f"{int(seconds)}s"

    return time_string.strip()


def file_created_within_60_minutes(file_path):
    # Get the creation time of the file
    creation_time = os.path.getctime(file_path)

    # Calculate the difference from the current time
    current_time = time.time()
    age_seconds = current_time - creation_time

    # Check if the file was created over 60 minutes ago
    return age_seconds < 60 * 60  # 60 minutes * 60 seconds


def get_race_name(distance):
    distance = int(distance)
    for race in RACES:
        if abs(distance - race['distance']) < 10:
            return race['name']
    return f"{distance} meters"

def get_race_distance(name):
    for race in RACES:
        if race["name"] == name:
            return race["distance"]
    return None

def format_time(elapsed_time):
    """Erase the leading zeros and colons"""
    time_str = str(elapsed_time)
    # Split the string at colons
    time_parts = time_str.split(':')
    new_parts = []
    strip = True
    for time_part in time_parts:
        if strip:
            time_part = time_part.lstrip('0')
        if time_part == '':
            continue
        elif strip:
            strip = False
        new_parts.append(time_part)
    
    # Join the parts back together with colons
    cleaned_time = ':'.join(new_parts)
    
    return cleaned_time

def min2minsec(total_minutes):
    # Calculate minutes and seconds
    minutes = int(total_minutes)
    seconds = int((total_minutes - minutes) * 60)
    
    # Format the result as "minutes:seconds"
    return f"{minutes}:{seconds:02d}"
