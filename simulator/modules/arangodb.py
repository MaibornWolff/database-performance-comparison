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
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 100)
    if batch_mode:
        batch_db = db.begin_batch_execution(return_result=False)
    collections = _get_collections(batch_db if batch_mode else db, config["use_multiple_tables"])

    print("Inserting events", flush=True)
    count = 0
    for idx, event in enumerate(events):
        collection = _select_collection(collections, config["use_multiple_tables"], idx)
        data = event.to_dict()
        if config["primary_key"] == "client":
            data["_key"] = f"{event.device_id}{event.timestamp}{event.sequence_number}"
        collection.insert(data, sync=sync)
        count += 1
        if batch_mode and count >= batch_size:
            batch_db.commit()
            count = 0
            batch_db = db.begin_batch_execution(return_result=False)
            collections = _get_collections(batch_db, config["use_multiple_tables"])
    if batch_mode:
        batch_db.commit()
    print("Finished inserting", flush=True)


def _get_collections(db, use_multiple_tables):
    if use_multiple_tables:
        return [db.collection(f"events{i}") for i in range(4)]
    else:
        return [db.collection("events")]


def _select_collection(collections, use_multiple_tables, idx):
    if use_multiple_tables:
        return collections[idx%4]
    else:
        return collections[0]
