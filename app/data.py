import logging
from app import db, client
from app.models import Activity, StreamData, BestEffort, User, Split, Segment
from app.auth import get_strava_athlete
from datetime import datetime
import time

logger = logging.getLogger("moovmetrics")

TYPES = ["time", "altitude", "heartrate", "temp", "velocity_smooth"]


def get_races(top_n: int | None = 5) -> list[Activity] | None:
    """Get race stats to use with LLM"""
    strava_athlete = get_strava_athlete()
    if not strava_athlete:
        logger.error("Error authenticating user")
        return None

    # Get just recent races
    if top_n:
        races = (
            Activity.query.filter_by(user_id=strava_athlete.id, workout_type=1)
            .order_by(Activity.start_date_local.desc())
            .limit(top_n)
            .all()
        )
    else:
        races = (
            Activity.query.filter_by(user_id=strava_athlete.id, workout_type=1)
            .order_by(Activity.start_date_local.desc())
            .all()
        )

    return races


def get_user():
    strava_athlete = get_strava_athlete()
    if not strava_athlete:
        logger.error("Error authenticating user")
        return None
    else:
        _update_user_database(strava_athlete)
        return strava_athlete


def get_activities(user_id, ids=None, update_db=False, top_n=None):
    """Fetch activities from the database, updating it if necessary.

    Returns:
        List
    """
    if update_db:
        _update_activities_database(user_id)
    if ids:
        return [Activity.query.filter_by(id=id, user_id=user_id).first() for id in ids]
    else:
        if top_n:
            return (
                Activity.query.filter_by(user_id=user_id)
                .order_by(Activity.start_date_local.desc())
                .limit(top_n)
                .all()
            )
        else:
            return (
                Activity.query.filter_by(user_id=user_id)
                .order_by(Activity.start_date_local.desc())
                .all()
            )


def get_stream_data_for_activity(strava_id, data_type):
    """Fetch stream data for an activity, updating the db if necessary.

    Args:
        strava_id: strava_id of activity in db
        data_type: name of the stream

    Returns:
        List
    """
    _update_streams_database(strava_id, data_type)
    return StreamData.query.filter_by(activity_id=strava_id, data_type=data_type).all()


def get_splits_for_activity(strava_id):
    _update_splits_segments(strava_id)
    return Split.query.filter_by(activity_id=strava_id).all()


def get_segments_for_activity(strava_id):
    _update_splits_segments(strava_id)
    return Segment.query.filter_by(activity_id=strava_id).all()


def _update_splits_segments(strava_id):
    strava_activity = client.get_activity(activity_id=strava_id)
    _update_splits_database(strava_id, strava_activity)
    _update_segments_database(strava_id, strava_activity)


def get_all_best_efforts(user_id, activities=None, batch_size=5):
    """Gets all the effort data for all the activities.

    The rate limit is avoided by waiting for 30 seconds each batch_size number
    of calls
    """
    if activities is None:
        activities = (
            Activity.query.filter_by(user_id=user_id, type="Run")
            .order_by(Activity.start_date_local.desc())
            .all()
        )

    all_best_efforts = []
    i = 0
    for activity in activities:
        best_efforts = BestEffort.query.filter_by(activity_id=activity.strava_id).all()
        if not best_efforts:
            logger.info(f"Getting activity number: {i}")
            best_efforts = get_pr_efforts_for_activity(activity.strava_id)
            i += 1
        all_best_efforts.extend(best_efforts)
        if i % batch_size == 0 and i > 0:
            time.sleep(30)
    return all_best_efforts


def _get_most_recent_activity_start_date(user_id):
    """Retrieve the most recent activity start date from the database."""
    most_recent_activity = (
        Activity.query.filter_by(user_id=user_id)
        .order_by(Activity.start_date_local.desc())
        .first()
    )
    if most_recent_activity:
        return most_recent_activity.start_date_local
    else:
        return None


def get_new_activities(after_date):
    """Retrieve new activities from the external source."""
    per_page = 100
    try:
        activities = list(client.get_activities(limit=per_page, after=after_date))
        all_activities = activities[:]
        while len(activities) == per_page:
            activities = list(
                client.get_activities(
                    limit=per_page, before=activities[-1].start_date, after=after_date
                )
            )
            all_activities.extend(activities)
        return all_activities
    except Exception as e:
        logging.error(f"Error fetching new activities: {e}")
        return []


def _update_activities_database(user_id):
    """Add new activities to the database."""
    existing_activity_ids = {
        int(activity.strava_id)
        for activity in Activity.query.filter_by(user_id=user_id)
    }
    after_date = _get_most_recent_activity_start_date(user_id)
    new_activities = get_new_activities(after_date)
    for activity in new_activities:
        if activity.id not in existing_activity_ids:
            try:
                new_activity = Activity(
                    strava_id=activity.id,
                    user_id=user_id,
                    achievement_count=activity.achievement_count,
                    # athlete=activity.athlete,
                    athlete_count=activity.athlete_count,
                    average_cadence=activity.average_cadence,
                    average_heartrate=activity.average_heartrate,
                    average_speed=activity.average_speed,
                    average_temp=activity.average_temp,
                    average_watts=activity.average_watts,
                    # bound_client=activity.bound_client,
                    calories=activity.calories,
                    comment_count=activity.comment_count,
                    commute=activity.commute,
                    description=activity.description,
                    device_name=activity.device_name,
                    device_watts=activity.device_watts,
                    distance=activity.distance,
                    elapsed_time=activity.elapsed_time,
                    elev_high=activity.elev_high,
                    elev_low=activity.elev_low,
                    embed_token=activity.embed_token,
                    external_id=activity.external_id,
                    flagged=activity.flagged,
                    from_accepted_tag=activity.from_accepted_tag,
                    gear=activity.gear,
                    gear_id=activity.gear_id,
                    guid=activity.guid,
                    has_heartrate=activity.has_heartrate,
                    has_kudoed=activity.has_kudoed,
                    hide_from_home=activity.hide_from_home,
                    instagram_primary_photo=activity.instagram_primary_photo,
                    kilojoules=activity.kilojoules,
                    kudos_count=activity.kudos_count,
                    map=activity.map.summary_polyline,
                    max_heartrate=activity.max_heartrate,
                    max_speed=activity.max_speed,
                    max_watts=activity.max_watts,
                    moving_time=activity.moving_time,
                    name=activity.name,
                    partner_brand_tag=activity.partner_brand_tag,
                    partner_logo_url=activity.partner_logo_url,
                    perceived_exertion=activity.perceived_exertion,
                    photo_count=activity.photo_count,
                    pr_count=activity.pr_count,
                    private=activity.private,
                    segment_leaderboard_opt_out=activity.segment_leaderboard_opt_out,
                    start_date_local=activity.start_date_local,
                    start_latitude=activity.start_latitude,
                    start_longitude=activity.start_longitude,
                    suffer_score=activity.suffer_score,
                    # timezone=activity.timezone,
                    total_elevation_gain=activity.total_elevation_gain,
                    total_photo_count=activity.total_photo_count,
                    trainer=activity.trainer,
                    type=activity.type,
                    upload_id=activity.upload_id,
                    upload_id_str=activity.upload_id_str,
                    # utc_offset=activity.utc_offset,
                    weighted_average_watts=activity.weighted_average_watts,
                    workout_type=activity.workout_type,
                )
                db.session.add(new_activity)
            except Exception as e:
                logging.error(f"Error adding new activity to database: {e}")
    try:
        db.session.commit()
    except Exception as e:
        logging.error(f"Error committing changes to database: {e}")
        db.session.rollback()


def _update_splits_database(strava_id, activity):
    try:
        existing_split_data = Split.query.filter_by(activity_id=strava_id).all()
        if existing_split_data:
            logging.info(f"Split data already exists for activity ID {strava_id}")
            return existing_split_data

        for split in activity.splits_standard:
            new_split = Split(
                activity_id=strava_id,
                split_num=split.split,
                average_speed=split.average_speed,
                average_heartrate=split.average_heartrate,
                average_grade_adjusted_speed=split.average_grade_adjusted_speed,
                elapsed_time=split.elapsed_time,
                distance=split.distance,
                pace_zone=split.pace_zone,
            )
            db.session.add(new_split)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error adding new splits to database for {strava_id}: {e}")
        db.session.rollback()


def _update_segments_database(strava_id, activity):
    try:
        existing_segment_data = Split.query.filter_by(activity_id=strava_id).all()
        if existing_segment_data:
            logging.info(f"Split data already exists for activity ID {strava_id}")
            return existing_segment_data

        for segment in activity.segment_efforts:
            new_segment = Split(
                activity_id=strava_id,
                strava_id=segment.id,
                name=segment.name,
                average_speed=segment.average_speed,
                average_heartrate=segment.average_heartrate,
                elapsed_time=segment.elapsed_time,
                distance=segment.distance,
            )
            db.session.add(new_segment)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error adding new segments to database for {strava_id}: {e}")
        db.session.rollback()


def _update_streams_database(strava_id, data_type=None):
    try:
        # Check if stream data already exists for the activity
        existing_stream_data = StreamData.query.filter_by(
            activity_id=strava_id, data_type=data_type
        ).all()
        if existing_stream_data:
            logging.info(f"Stream data already exists for activity ID {strava_id}")
            return existing_stream_data

        # Fetch stream data for each type from external source
        time_stream_data, streams = _get_stream_data(strava_id)
        for stream_name, stream in streams.items():
            for time, value in zip(time_stream_data, stream.data):
                stream_data_entry = StreamData(
                    activity_id=strava_id, data_type=stream_name, time=time, value=value
                )
                db.session.add(stream_data_entry)

        db.session.commit()
        logging.info(
            f"Stream data successfully fetched and stored for activity ID {strava_id}"
        )
    except Exception as e:
        logging.error(
            f"Error fetching and storing stream data for activity ID {strava_id}: {e}"
        )
        db.session.rollback()




def _update_user_database(athlete):
    existing_athlete = User.query.filter_by(strava_id=athlete.id).first()
    if existing_athlete:
        return

    try:
        username = athlete.username
        if not username:
            username = ""
            if athlete.firstname:
                username += athlete.firstname
            if athlete.lastname:
                username += athlete.lastname[0].capitalize()
            if username == "":
                username = str(athlete.id)
        new_athlete = User(strava_id=athlete.id, username=username, email=athlete.email)
        db.session.add(new_athlete)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error with saving user: {athlete.id}")
        db.session.rollback()


_STRAVA_DISTANCES = {400, 805, 1000, 1609, 3219, 5000, 10000, 15000, 16093, 20000, 21097, 42195}

def _is_strava_distance(distance):
    return any(abs(distance - d) < 2 for d in _STRAVA_DISTANCES)


def get_pr_efforts_for_activity(strava_id):
    """Fetch the detailed activity from Strava and store only all-time PR efforts (pr_rank == 1)."""
    existing = BestEffort.query.filter_by(activity_id=strava_id).all()
    if existing:
        # If existing entries have old-style distances (not from Strava API), delete and re-fetch
        if any(not _is_strava_distance(e.distance) for e in existing):
            for e in existing:
                db.session.delete(e)
            db.session.commit()
        else:
            return existing

    try:
        strava_activity = client.get_activity(activity_id=strava_id)
        raw_efforts = strava_activity.best_efforts or []

        if not raw_efforts:
            db.session.add(BestEffort(activity_id=strava_id, race_name="__none__", distance=0, elapsed_time=None))
            db.session.commit()
            return []

        best_efforts = []
        for effort in raw_efforts:
            if effort.pr_rank != 1 or effort.elapsed_time is None or effort.distance is None or not effort.name:
                continue
            be = BestEffort(
                activity_id=strava_id,
                race_name=effort.name.lower(),
                distance=float(effort.distance),
                elapsed_time=effort.elapsed_time.total_seconds(),
            )
            db.session.add(be)
            best_efforts.append(be)
        db.session.commit()
        logging.info(f"PR efforts stored for activity: {strava_id} ({len(best_efforts)} PRs)")
        return best_efforts
    except Exception as e:
        logger.error(f"[DEBUG best_efforts] activity {strava_id}: exception: {e}")
        db.session.rollback()
        return []


def _get_stream_data(strava_id):
    streams = client.get_activity_streams(strava_id, types=TYPES, resolution="medium")
    time_stream = streams.pop("time", None)
    if time_stream is None:
        raise ValueError("Time stream data is missing")

    return time_stream.data, streams
