from datetime import datetime
from app import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strava_id = db.Column(db.String(100), unique=True, nullable=False)  # Store Strava's unique user ID
    username = db.Column(db.String(20), unique=True, nullable=False)    # Optional: username for your application
    email = db.Column(db.String(120), unique=True)       # Optional: email address
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Add more fields as needed, such as profile information, preferences, etc.
    activities = db.relationship("Activity", backref="user", lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"
    
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    strava_id = db.Column(db.String(100), unique=True, nullable=False)  # Strava's unique activity ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Foreign key to associate activity with user
    achievement_count = db.Column(db.Integer)  # int | None
    athlete = db.Column(db.String)  # stravalib.model.Athlete | None
    athlete_count = db.Column(db.Integer)  # int | None
    average_cadence = db.Column(db.Float)  # float | None
    average_heartrate = db.Column(db.Float)  # float | None
    average_speed = db.Column(db.Float)  # float | None
    average_temp = db.Column(db.Integer)  # int | None
    average_watts = db.Column(db.Float)  # float | None
    bound_client = db.Column(db.String)  # Any | None
    calories = db.Column(db.Float)  # float | None
    comment_count = db.Column(db.Integer)  # int | None
    commute = db.Column(db.Boolean)  # bool | None
    description = db.Column(db.String)  # str | None
    device_name = db.Column(db.String)  # str | None
    device_watts = db.Column(db.Boolean)  # bool | None
    distance = db.Column(db.Float)  # float | None
    elapsed_time = db.Column(db.Interval)  # datetime.timedelta | None
    elev_high = db.Column(db.Float)  # float | None
    elev_low = db.Column(db.Float)  # float | None
    embed_token = db.Column(db.String)  # str | None
    external_id = db.Column(db.String)  # str | None
    flagged = db.Column(db.Boolean)  # bool | None
    from_accepted_tag = db.Column(db.Boolean)  # bool | None
    gear = db.Column(db.String)  # stravalib.model.Gear | None
    gear_id = db.Column(db.String)  # str | None
    guid = db.Column(db.String)  # str | None
    has_heartrate = db.Column(db.Boolean)  # bool | None
    has_kudoed = db.Column(db.Boolean)  # bool | None
    hide_from_home = db.Column(db.Boolean)  # bool | None
    instagram_primary_photo = db.Column(db.String)  # str | None
    kilojoules = db.Column(db.Float)  # float | None
    kudos_count = db.Column(db.Integer)  # int | None
    # laps
    location_city = db.Column(db.String)
    location_country = db.Column(db.String)
    location_state = db.Column(db.String)
    manual = db.Column(db.Boolean)
    map = db.Column(db.String)
    max_heartrate = db.Column(db.Integer)  # int | None
    max_speed = db.Column(db.Float)  # float | None
    max_watts = db.Column(db.Integer)  # int | None
    moving_time = db.Column(db.Interval)  # datetime.timedelta | None
    name = db.Column(db.String)  # str | None
    partner_brand_tag = db.Column(db.String)  # str | None
    partner_logo_url = db.Column(db.String)  # str | None
    perceived_exertion = db.Column(db.Integer)  # int | None
    photo_count = db.Column(db.Integer)  # int | None
    # Photos
    pr_count = db.Column(db.Integer)  # int | None
    private = db.Column(db.Boolean)  # bool | None
    # segment_efforts
    segment_leaderboard_opt_out = db.Column(db.Boolean)  # bool | None
    # splits_metrics
    # splits_standard
    # sport_type
    start_date_local = db.Column(db.DateTime)
    start_latitude = db.Column(db.Float)
    # start_latlng
    start_longitude = db.Column(db.Float)
    suffer_score = db.Column(db.Integer)  # int | None
    timezone = db.Column(db.String)  # str | None
    total_elevation_gain = db.Column(db.Float)  # float | None
    total_photo_count = db.Column(db.Integer)  # int | None
    trainer = db.Column(db.Boolean)  # bool | None
    type = db.Column(db.String)  # str | None
    upload_id = db.Column(db.Integer)  # int | None
    upload_id_str = db.Column(db.String)  # str | None
    utc_offset = db.Column(db.Float)  # float | None
    weighted_average_watts = db.Column(db.Integer)  # int | None
    workout_type = db.Column(db.Integer)  # int | None

    stream_data = db.relationship("StreamData", backref="activity", lazy=True)
    best_efforts = db.relationship("BestEffort", backref="activity", lazy=True)

    def __repr__(self):
        return f"Activity('{self.strava_id}', '{self.start_time}')"
    
class StreamData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.strava_id'), nullable=False)
    data_type = db.Column(db.String)
    time = db.Column(db.Integer, nullable=False)  # Timestamp
    value = db.Column(db.Integer, nullable=False)  # Heart rate value


class BestEffort(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.strava_id'), nullable=False)
    race_name = db.Column(db.String(100), nullable=False)
    distance = db.Column(db.Float, nullable=False)
    elapsed_time = db.Column(db.Float)


class Split(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.strava_id'), nullable=False)
    split_num = db.Column(db.String(100), nullable=False)
    average_speed = db.Column(db.Float)
    average_heartrate = db.Column(db.Float)
    average_grade_adjusted_speed = db.Column(db.Float)
    elapsed_time = db.Column(db.Interval)
    distance = db.Column(db.Float)
    pace_zone = db.Column(db.Integer)

class Segment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.strava_id'), nullable=False)
    strava_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    average_speed = db.Column(db.Float)
    average_heartrate = db.Column(db.Float)
    elapsed_time = db.Column(db.Interval)
    distance = db.Column(db.Float)
    pace_zone = db.Column(db.Integer)
