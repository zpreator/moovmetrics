# stravapp

Strava companion app to explore deeper analysis including:
- Heatmap of activities
- Personal bests
- Targeted trends
- more to come

[Dev](http://stravapp-dev-99f4f17c9e2f.herokuapp.com/dashboard)
[Prod](http://stravapp-prod-f3bda259aecb.herokuapp.com/dashboard)

# Installation

## Clone this repository
```commandline
git clone https://github.com/zpreator/stravapp.git
```

## Enter the folder
```commandline
cd stravapp
```

## Create and activate virtual environment (I usually use PyCharm to do this step)
```commandline
python -m venv venv
```

## Check your system 1 or 2
### 1 Windows
```commandline
venv\scripts\activate
```

### 2 Linux/Mac
```commandline
source venv/bin/activate
```
## Get requirements
```commandline
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Set up Client ID and Client Secret with Strava
1. If you have not already, go to https://www.strava.com/register and sign up for a Strava account.
2. After you are logged in, go to https://www.strava.com/settings/api and create an app.
   1. Use www.example.com or anything else for the website and authorization callback domain
3. When the app is created, take note of the Client ID and Client Secret
4. Rename the file settings-template to settings.env 
   1. Replace the <> sections in the file
   ```
   STRAVA_CLIENT_ID = <client_id>
   STRAVA_CLIENT_SECRET = "<client_secret>"
   ```
   
## Run
```commandline
python server.py
```
