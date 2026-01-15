#!/bin/bash

# Download Xray core (if not present)
if [ ! -f "xray" ]; then
    echo "Downloading Xray core..."
    curl -L -o xray.zip https://github.com/XTLS/Xray-core/releases/download/v1.8.4/Xray-linux-64.zip
    unzip xray.zip xray
    chmod +x xray
    rm xray.zip
fi

# Start Xray in background
echo "Starting Xray proxy..."
./xray -config config.json &

# Wait for Xray to start
sleep 2

# Start the application
echo "Starting application..."
gunicorn new_app:app
