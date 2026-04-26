from kafka import KafkaConsumer
import json

KAFKA_BROKER = "localhost:9092"
TOPIC = "f1-telemetry"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BROKER,
    auto_offset_reset="earliest",
    value_deserializer=lambda v: json.loads(v.decode("utf-8"))
)

print(f"Consumer started — listening to topic: {TOPIC}")

count = 0
for message in consumer:
    record = message.value
    count += 1
    if count % 1000 == 0:
        print(f"Consumed {count} records — latest: driver {record.get('driver_number')} at {record.get('date')}")