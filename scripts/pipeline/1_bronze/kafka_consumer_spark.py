from databricks.connect import DatabricksSession
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import *

spark = DatabricksSession.builder.serverless(True).getOrCreate()

KAFKA_BROKER = "localhost:9092"
TOPIC = "f1-telemetry"
BRONZE_TABLE = "formone.bronze.streaming_telemetry"

schema = StructType([
    StructField("date", StringType()),
    StructField("driver_number", IntegerType()),
    StructField("rpm", IntegerType()),
    StructField("speed", IntegerType()),
    StructField("n_gear", IntegerType()),
    StructField("throttle", IntegerType()),
    StructField("brake", IntegerType()),
    StructField("drs", IntegerType()),
    StructField("session_key", IntegerType()),
    StructField("meeting_key", IntegerType())
])

df = (spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BROKER)
    .option("subscribe", TOPIC)
    .option("startingOffsets", "latest")
    .load()
)

parsed = (df
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withColumn("ingested_at", current_timestamp())
)

query = (parsed.writeStream
    .format("delta")
    .outputMode("append")
    .trigger(availableNow=True)
    .option("checkpointLocation", "dbfs:/Volumes/formone/bronze/checkpoints/f1_telemetry")
    .toTable(BRONZE_TABLE)
)

query.awaitTermination()