import requests
import json
import time
from kafka import KafkaProducer

KAFKA_BROKER = "localhost:9092"
TOPIC = "f1-telemetry"
SESSION_KEY = 9693  # Melbourne 2025 Race
POLL_INTERVAL = 3
DRIVER_NUMBERS = [1, 4, 6, 10, 11, 14, 16, 18, 20, 22, 23, 24, 27, 30, 31, 38, 44, 55, 63, 81]

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

print(f"Producer started — session: {SESSION_KEY} — topic: {TOPIC}")

last_timestamp = "2025-03-16T04:00:00"  # session start time
batch_minutes = 5  # fetch 5 minutes of data per poll

while True:
    try:
        from datetime import datetime, timedelta
        start = datetime.fromisoformat(last_timestamp)
        end = start + timedelta(minutes=batch_minutes)

        url = (
            f"https://api.openf1.org/v1/car_data"
            f"?session_key={SESSION_KEY}"
            f"&date>={start.isoformat()}"
            f"&date<{end.isoformat()}"
        )

        r = requests.get(url, timeout=15)
        data = r.json()

        if isinstance(data, list) and len(data) > 0:
            for record in data:
                producer.send(TOPIC, value=record)
            producer.flush()
            last_timestamp = end.isoformat()
            print(f"Published {len(data)} records — window: {start.isoformat()} → {end.isoformat()}")
        else:
            print(f"No more data — replay complete. Response: {data}")
            break

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

    time.sleep(POLL_INTERVAL)