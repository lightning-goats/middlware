#!/usr/bin/env python
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)


socketio = SocketIO(app, cors_allowed_origins="*")

# Create a list to store received JSON data
received_data = []

# Route to handle URL parameters
@app.route('/weather', methods=['GET'])
def receive_url_parameters():
    try:
        # Clear the existing data
        received_data.clear()

        data = {
            "dateutc": request.args.get("dateutc"),
            "tempinf": float(request.args.get("tempinf", 0.0)),
            "humidityin": int(request.args.get("humidityin", 0)),
            "baromrelin": float(request.args.get("baromrelin", 0.0)),
            "baromabsin": float(request.args.get("baromabsin", 0.0)),
            "tempf": float(request.args.get("tempf", 0.0)),
            "humidity": int(request.args.get("humidity", 0)),
            "winddir": int(request.args.get("winddir", 0)),
            "windspeedmph": float(request.args.get("windspeedmph", 0.0)),
            "windgustmph": float(request.args.get("windgustmph", 0.0)),
            "maxdailygust": float(request.args.get("maxdailygust", 0.0)),
            "hourlyrainin": float(request.args.get("hourlyrainin", 0.0)),
            "eventrainin": float(request.args.get("eventrainin", 0.0)),
            "dailyrainin": float(request.args.get("dailyrainin", 0.0)),
            "weeklyrainin": float(request.args.get("weeklyrainin", 0.0)),
            "monthlyrainin": float(request.args.get("monthlyrainin", 0.0)),
            "totalrainin": float(request.args.get("totalrainin", 0.0)),
            "solarradiation": float(request.args.get("solarradiation", 0.0)),
            "uv": int(request.args.get("uv", 0)),
            "batt_co2": int(request.args.get("batt_co2", 0))
        }
        
        # Log the received data
        logging.info(f"Received data: {data}")

        # Store the received JSON data
        received_data.append(data)
        
        # Send the updated data via WebSocket
        socketio.emit('new_data', data)
        
        return 'URL parameters received successfully', 200
    
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return 'Failed to receive URL parameters', 400

# Route to retrieve all stored data                                                                                        
@app.route('/get_received_data', methods=['GET'])                                                                          
def get_received_data():                                                                                                   
    return jsonify(received_data)

#Event for handling a new WebSocket connection
@socketio.on('connect')
def handle_connect():
    logging.info('Client connected')

# Event for handling disconnection
@socketio.on('disconnect')
def handle_disconnect():
    logging.info('Client disconnected')

# Start the Flask-SocketIO server
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
