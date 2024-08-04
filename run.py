from app import app
import os

if __name__ == "__main__":
    # Use the PORT environment variable provided by Heroku
    port = int(os.environ.get('PORT', 5001))

    # Run the app
    app.run(host='0.0.0.0', port=port, debug=True)