from datetime import date, timedelta
import time
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import urllib3
from .config import config

urllib3.disable_warnings()

def _db():
    client = Elasticsearch(config["endpoint"], verify_certs=False)
    return client


def init():
    client = _db()

    if config["clean_database"] and client.indices.exists("events"):
        client.indices.delete("events")
    
    if not client.indices.exists("events"):
        client.indices.create("events", """{
            "mappings": {
                "properties": {
                    "timestamp": { "type": "date", "format": "epoch_millis" },
                    "device_id": { "type": "keyword" },
                    "sequence_number": { "type": "long" },
                    "temperature": { "type": "float" }
                }
            },
            "settings": {
                "index": {
                    "number_of_shards": 3,  
                    "number_of_replicas": 2 
                }
            }
        }""")
    print("Created index")


def prefill_events(events):
    _insert_events(events, True, 10000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1000)
    _insert_events(events, batch_mode, batch_size)


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    client = _db()

    print("Inserting events", flush=True)
    if batch_mode:
        _batch_mode(client, events, batch_size)
    else:
        _single_insert_mode(client, events)

    print("Finished inserting", flush=True)


def _batch_mode(client, events, batch_size):
    gen_id = config.get("primary_key", "db") == "client"
    values = list()
    count = 0
    for event in events:
        document = {
            "_index": "events",
            "timestamp": event.timestamp,
            "device_id": event.device_id,
            "sequence_number": event.sequence_number,
            "temperature": event.temperature,
        }
        if gen_id:
            document["_id"] = f"{event.device_id}{event.timestamp}{event.sequence_number}"
        values.append(document)
        count += 1
        if count >= batch_size:
            bulk(client, values)
            values.clear()
            count = 0
    bulk(client, values)
        


def _single_insert_mode(client, events):
    gen_id = config.get("primary_key", "db") == "client"
    for event in events:
        document = {
            "timestamp": event.timestamp,
            "device_id": event.device_id,
            "sequence_number": event.sequence_number,
            "temperature": event.temperature,
        }
        if gen_id:
            client.index(index="events", id=f"{event.device_id}{event.timestamp}{event.sequence_number}", document=document)
        else:
            client.index(index="events", document=document)


_queries = {
    "count-events": "",
    "temperature-min-max": {
        "aggs": {
            "temperature_min": { "min": { "field": "temperature" } },
            "temperature_max": { "max": { "field": "temperature" } }
        }
    },
    "temperature-stats": {
        "aggs": {
            "temperature_min": { "min": { "field": "temperature" } },
            "temperature_max": { "max": { "field": "temperature" } },
            "temperature_avg": { "avg": { "field": "temperature" } }
        }
    },
    "temperature-stats-per-device": {
        "aggs": {
            "devices": {
                "terms": { "field": "device_id", "size": 100000 },
                "aggs": {
                    "temperature_stats": { "stats": { "field": "temperature"} }
                }
            }
        }
    },
    "newest-per-device": {
        "aggs": {
            "devices": {
                "terms": { "field": "device_id", "size": 100000 },
                "aggs": {
                    "newest": { "top_hits": { 
                        "sort": [{ "timestamp": { "order": "desc" }}],
                        "_source": { 
                            "includes": ["temperature"]
                        },
                        "size": 1
                    }}
                }
            }
        }
    },
}

def queries():
    client = _db()

    if "queries" in config:
        included = config["queries"].split(",")
        for key in list(_queries.keys()):
            if key not in included:
                del _queries[key]

    query_times = dict([(name, []) for name in _queries.keys()])
    for i in range(int(config["runs"])):
        for name, query in _queries.items():
            print(f"Executing query {name}", flush=True)
            start = time.time()
            if name == "count-events":
                result = client.cat.count("events", request_timeout=600)
                print(result, flush=True)
            else:
                result = client.search(index="events", body=query, size=0, request_timeout=600)
                print(result, flush=True)
            duration = time.time() - start
            print("Finished query", flush=True)
            query_times[name].append(duration)

    return query_times
