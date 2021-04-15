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

    if config["clean_database"]:
        for table_name in ["events0", "events1", "events2", "events3", "events"]:
            db.delete_collection(table_name, ignore_missing=True)

    shard_count = int(config.get("shard_count")) if "shard_count" in config else None
    for table_name in table_names:
        if config["clean_database"] or not db.has_collection(table_name):
            db.create_collection(table_name, shard_count=shard_count, replication_factor=int(config.get("replication_factor", 1)))
    print("Created table events")


def prefill_events(events):
    _insert_events(events, True, 1000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 100)
    _insert_events(events, batch_mode, batch_size)


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    sync = config.get("sync", "False").lower() in ["true", "yes", "1"]
    db = _db()
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        collections = [db.collection(f"events{i}") for i in range(4)]
    else:
        collections = [db.collection("events")]

    print("Inserting events", flush=True)
    if batch_mode:
        count = 0
        docs_for_collections = [list() for _ in range(4 if use_multiple_tables else 1)]

        for idx, event in enumerate(events):
            data = event.to_dict()
            if config["primary_key"] == "client":
                data["_key"] = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            if use_multiple_tables:
                docs_for_collections[idx%4].append(data)
            else:
                docs_for_collections[0].append(data)
            count += 1
            if count >= batch_size:
                for col_index, docs in enumerate(docs_for_collections):
                    collections[col_index].insert_many(docs, sync=sync)
                    docs.clear()
                count = 0
        for col_index, docs in enumerate(docs_for_collections):
            if len(docs) > 0:
                collections[col_index].insert_many(docs, sync=sync)

    else:
        for idx, event in enumerate(events):
            if use_multiple_tables:
                collection = collections[idx%4]
            else:
                collection = collections[0]
            data = event.to_dict()
            if config["primary_key"] == "client":
                data["_key"] = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            collection.insert(data, sync=sync)
    print("Finished inserting", flush=True)
