from datetime import date, timedelta
import time
import influxdb_client
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS, WritePrecision
from .config import config


BUCKET_NAME = "dbtest"
CURRENT_YEAR = date.today().year
NEXT_YEAR = (date.today() + timedelta(days=366)).year


def _db():
    client = influxdb_client.InfluxDBClient(url=config["endpoint"], token=config["token"], org=config["org"], timeout=600*1000)
    return client


def init():
    client = _db()
    buckets_api = client.buckets_api()

    bucket = buckets_api.find_bucket_by_name(BUCKET_NAME)
    if config["clean_database"]:
        if bucket:
            buckets_api.delete_bucket(bucket.id)
            bucket = None
    
    if not bucket:
        buckets_api.create_bucket(bucket_name=BUCKET_NAME)

    print("Created bucket")


def prefill_events(events):
    _insert_events(events, True, 1000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1000)
    _insert_events(events, batch_mode, batch_size)


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    client = _db()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    print("Inserting events", flush=True)
    if batch_mode:
        _batch_mode(write_api, events, batch_size)
    else:
        _single_insert_mode(write_api, events)

    print("Finished inserting", flush=True)


def _single_insert_mode(write_api, events):
    for event in events:
        p = Point("events").time(event.timestamp, write_precision=WritePrecision.MS).tag("device_id", event.device_id).field("temperature", event.temperature)
        write_api.write(bucket=BUCKET_NAME, record=p)


def _batch_mode(write_api, events, batch_size):
    buffer = []
    size = 0
    for event in events:
        p = Point("events").time(event.timestamp, write_precision=WritePrecision.MS).tag("device_id", event.device_id).field("temperature", event.temperature)
        buffer.append(p)
        size += 1
        if size >= batch_size:
            write_api.write(bucket=BUCKET_NAME, record=buffer)
            buffer.clear()
            size = 0
    if size >= 0:
        write_api.write(bucket=BUCKET_NAME, record=buffer) 


_queries = {
    "count-events": f"""
        from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> count()
        |> group()
        |> sum(column: "_value")
    """,
    "temperature-min-max": f"""
        max = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["_value"])
        |> max()
        |> group()
        |> max()
        |> map(fn: (r) => ({{ r with dummy: "1" }}))
        min = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["_value"])
        |> min()
        |> group()
        |> min()
        |> map(fn: (r) => ({{ r with dummy: "1" }}))
        join(tables: {{max: max, min: min}}, on: ["dummy"])
        |> keep(columns: ["_value_min", "_value_max"])
    """,
    "temperature-stats": f"""
        mean = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["_value"])
        |> group()
        |> mean()
        |> map(fn: (r) => ({{ r with dummy: "1" }}))
        min = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["_value"])
        |> min()
        |> group()
        |> min()
        |> map(fn: (r) => ({{ r with dummy: "1" }}))
        max = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["_value"])
        |> max()
        |> group()
        |> max()
        |> map(fn: (r) => ({{ r with dummy: "1" }}))
        join1 = join(tables: {{mean: mean, min: min}}, on: ["dummy"])
        join(tables: {{join1: join1, max:max}}, on: ["dummy"])
    """,
    "temperature-stats-per-device": f"""
        mean = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["device_id", "_value"])
        |> mean()
        |> group()
        max = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["device_id", "_value"])
        |> max()
        |> group()
        min = from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> keep(columns: ["device_id", "_value"])
        |> min()
        |> group()
        join1 = join(tables: {{mean: mean, max: max}}, on: ["device_id"])
        join(tables: {{join1: join1, min: min}}, on: ["device_id"])
    """,
    "newest-per-device": f"""
        from(bucket: "{BUCKET_NAME}")
        |> range(start: {CURRENT_YEAR}-01-01, stop: {NEXT_YEAR}-12-31)
        |> last()
        |> keep(columns: ["device_id", "_value"])
        |> group()
    """,
}

def queries():
    client = _db()
    query_api = client.query_api()

    query_times = dict([(name, []) for name in _queries.keys()])
    for i in range(int(config["runs"])):
        for name, query in _queries.items():
            start = time.time()
            result = query_api.query(query=query)
            list(result) # Force client to actually fetch results
            duration = time.time() - start
            query_times[name].append(duration)

    return query_times
