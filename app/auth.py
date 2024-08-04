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
    client.access_token = session['access_token']
    strava_athlete = client.get_athlete()
    return strava_athlete


def authenticate():
    """ Refreshes the current strava token

    Args:
        None

    Returns:
        bool
    
    The token_expires_at time is stored in the session and
    if the current time is past then do a refresh using the
    client.exchange_code_for_token
    """
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
                # The user will need to reauthenticate
                logger.error('Could not refresh, not authenticated')
                return False
            except Exception as e:
                logger.error(f"Unkown error: {e}")
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