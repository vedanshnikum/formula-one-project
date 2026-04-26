import json
import time
from kafka import KafkaConsumer
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

KAFKA_BROKER = "localhost:9092"
TOPIC = "f1-telemetry"
BRONZE_TABLE = "formone.bronze.streaming_telemetry"
WAREHOUSE_ID = "528397b2a432db12"  # your serverless warehouse ID

client = WorkspaceClient()
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BROKER,
    auto_offset_reset="latest",
    value_deserializer=lambda v: json.loads(v.decode("utf-8"))
)

print("Consumer started — writing to Databricks Delta...")

batch = []
BATCH_SIZE = 500

for message in consumer:
    record = message.value
    batch.append(record)

    if len(batch) >= BATCH_SIZE:
        values = ", ".join([
            f"('{r['date']}', {r['driver_number']}, {r['rpm']}, {r['speed']}, "
            f"{r['n_gear']}, {r['throttle']}, {r['brake']}, {r['drs']}, "
            f"{r['session_key']}, {r['meeting_key']}, current_timestamp())"
            for r in batch
        ])

        sql = f"""
        INSERT INTO {BRONZE_TABLE}
        (date, driver_number, rpm, speed, n_gear, throttle, brake, drs, session_key, meeting_key, ingested_at)
        VALUES {values}
        """

        response = client.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=sql,
            wait_timeout="30s"
        )

        print(f"Inserted {len(batch)} records — status: {response.status.state}")
        batch = []