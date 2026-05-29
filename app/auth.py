from app import client
from flask import session
import stravalib
import logging
import os
import time

logger = logging.getLogger("moovmetrics")

def get_strava_athlete():
    authenticated = authenticate()
    if not authenticated:
        return None
    if "strava_athlete" not in session:
        client.access_token = session.get("access_token")
        strava_athlete = client.get_athlete()
        session["strava_athlete"] = strava_athlete.to_dict()
    athlete = session["strava_athlete"]

    # Wrap dict in a simple object for attribute access
    class AthleteObj:
        def __init__(self, d):
            self.__dict__ = d

    if isinstance(athlete, dict):
        return AthleteObj(athlete)
    return athlete


def authenticate():
    """Refreshes the current strava token

    Args:
        None

    Returns:
        bool

    The token_expires_at time is stored in the session and
    if the current time is past then do a refresh using the
    client.exchange_code_for_token
    """
    if "token_expires_at" in session:
        if time.time() > session["token_expires_at"]:
            if "refresh_token" not in session:
                return False
            try:
                response = client.refresh_access_token(
                    client_id=int(os.environ["STRAVA_CLIENT_ID"]),
                    client_secret=os.environ["STRAVA_CLIENT_SECRET"],
                    refresh_token=session["refresh_token"],
                )
            except stravalib.exc.AccessUnauthorized:
                logger.error("Could not refresh token: not authorized")
                return False
            except Exception as e:
                logger.error(f"Unknown error refreshing token: {e}")
                return False

            # Store access token in the session for the user
            session["access_token"] = response["access_token"]
            session["refresh_token"] = response["refresh_token"]
            session["token_expires_at"] = response["expires_at"]
            return True
        else:
            return True
    else:
        return False
