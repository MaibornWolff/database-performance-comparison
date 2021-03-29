import os
from arango import ArangoClient
from .config import config


def _db():
    client = ArangoClient(hosts=config["endpoint"])
    db = client.db(config["database"], username=config["username"], password=config["password"])
    return db


def init():
    db = _db()
    
    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    for table_name in ["events0", "events1", "events2", "events3", "events"]:
        db.delete_collection(table_name, ignore_missing=True)

    shard_count = int(config.get("shard_count")) if "shard_count" in config else None
    for table_name in table_names:
        db.create_collection(table_name, shard_count=shard_count, replication_factor=int(config.get("replication_factor", 1)))
    print("Created table events")


def insert_events(events):
    print("Connecting to database", flush=True)
    sync = config.get("sync", "False").lower() in ["true", "yes", "1"]
    db = _db()
    if config["use_multiple_tables"]:
        collections = [db.collection(f"events{i}") for i in range(4)]
    else:
        collection = db.collection("events")

    print("Inserting events", flush=True)
    for idx, event in enumerate(events):
        if config["use_multiple_tables"]:
            collection = collections[idx%4]
        data = event.to_dict()
        if config["primary_key"] == "client":
            data["_key"] = f"{event.device_id}{event.timestamp}{event.sequence_number}"
        collection.insert(data, sync=sync)

    print("Finished inserting", flush=True)
