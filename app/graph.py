from app.utils import calculate_VO2_max, mps2mph, meters2miles
import logging
import numpy as np
from stravalib import unithelper
import pandas as pd

logger = logging.getLogger("moovmetrics")

def get_trends(activities, activity_types='all'):
    activity_list = []
    activities.reverse()
    for i, activity in enumerate(activities):
        has_hr = bool(activity.average_heartrate)
        type_ok = activity_types[0] == 'all' or (getattr(activity, 'type', None) and activity.type.lower() in activity_types)
        if has_hr and type_ok:
            try:
                avg_speed = round(float(mps2mph(activity.average_speed)), 2)
                vo2_max = calculate_VO2_max(activity)
                activity_list.append({
                    'date': activity.start_date_local,
                    'hr': activity.average_heartrate,
                    'avg_speed': avg_speed,
                    'kudos': activity.kudos_count,
                    'vo2_max': vo2_max,
                    'pr_count': activity.pr_count,
                    'distance': round(float(meters2miles(activity.distance)), 2)
                })
            except Exception as e:
                logger.warning(f"Error processing activity {i} for trends: {e}")
    if not activity_list:
        empty = {w: {'title': t, 'dates': [], 'values': {k: [] for k in ('hr','avg_speed','kudos','vo2_max','pr_count','distance')}}
                 for w, t in [('w','Last 7 days'),('m','Last 30 days'),('6m','Last 6 months'),('y','Last 12 months')]}
        empty['units'] = {'hr': 'bpm', 'avg_speed': 'mph', 'kudos': 'count'}
        return empty

    activities_df = pd.DataFrame(activity_list)
    activities_df['date'] = pd.to_datetime(activities_df['date'])
    activities_df.set_index('date', inplace=True)
    activities_df = activities_df.fillna(np.nan).replace([np.nan], [None])

    df_w = activities_df.resample('D').mean().round(2).tail(7).replace([np.nan], [None])
    df_d = activities_df.resample('D').mean().round(2).tail(30).replace([np.nan], [None])
    df_6m = activities_df.resample('W').mean().round(2).tail(6 * 4).replace([np.nan], [None])  # 6 months, at 4 weeks per month
    df_y = activities_df.resample('ME').mean().round(2).tail(12).replace([np.nan], [None])  # 12 months

    data = {
        'units':{
            'hr': 'bpm',
            'avg_speed': 'mph',
            'kudos': 'count'
        },
        'w': {
            'title': 'Last 7 days',
            'dates': df_w.index.strftime("%b %d").tolist(),
            'values': {
                'hr': df_w['hr'].tolist(),
                'avg_speed': df_w['avg_speed'].tolist(),
                'kudos': df_w['kudos'].tolist(),
                'vo2_max': df_w['vo2_max'].tolist(),
                'pr_count': df_w['pr_count'].tolist(),
                'distance': df_w['distance'].tolist()
            }
        },
        'm': {
            'title': 'Last 30 days',
            'dates': df_d.index.strftime("%b %d").tolist(),
            'values': {
                'hr': df_d['hr'].tolist(),
                'avg_speed': df_d['avg_speed'].tolist(),
                'kudos': df_d['kudos'].tolist(),
                'vo2_max': df_d['vo2_max'].tolist(),
                'pr_count': df_d['pr_count'].tolist(),
                'distance': df_d['distance'].tolist()
            }
        },
        '6m': {
            'title': 'Last 6 months',
            'dates': df_6m.index.strftime("%b %d %y").tolist(),
            'values': {
                'hr': df_6m['hr'].tolist(),
                'avg_speed': df_6m['avg_speed'].tolist(),
                'kudos': df_6m['kudos'].tolist(),
                'vo2_max': df_6m['vo2_max'].tolist(),
                'pr_count': df_6m['pr_count'].tolist(),
                'distance': df_6m['distance'].tolist()
            }
        },
        'y': {
            'title': 'Last 12 months',
            'dates': df_y.index.strftime("%b %y").tolist(),
            'values': {
                'hr': df_y['hr'].tolist(),
                'avg_speed': df_y['avg_speed'].tolist(),
                'kudos': df_y['kudos'].tolist(),
                'vo2_max': df_y['vo2_max'].tolist(),
                'pr_count': df_y['pr_count'].tolist(),
                'distance': df_y['distance'].tolist()
            }
        }

    }
    return data