import psycopg2
from .config import config


def _db():
    connection_string = config["connection_string"]
    con = psycopg2.connect(connection_string)
    if not config.get("batch_mode", False):
        con.set_session(autocommit=True)
    return con


def init():
    db = _db()
    cur = db.cursor()
    
    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    if config["clean_database"]:
        for table_name in ["events0", "events1", "events2", "events3", "events"]:
            cur.execute(f"""DROP TABLE IF EXISTS {table_name}""")
        db.commit()
    pk_column = "serial" if config["primary_key"] == "db" else "varchar"

    for table_name in table_names:
        cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (id {pk_column} PRIMARY KEY,
            timestamp bigint,
            device_id varchar,
            sequence_number bigint,
            temperature real
            )
        """)
    db.commit()
    print("Created table events")
    cur.close()


def prefill_events(events):
    _insert_events(events, True, 1000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 100)
    _insert_events(events, batch_mode, batch_size)


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    db = _db()
    cur = db.cursor()

    print("Inserting events", flush=True)
    count = 0
    for idx, event in enumerate(events):
        if config["use_multiple_tables"]:
            table_name = f"events{idx%4}"
        else:
            table_name = "events"
        
        if config["primary_key"] == "db":
            cur.execute(f"INSERT INTO {table_name} (timestamp, device_id, sequence_number, temperature) VALUES (%s, %s, %s, %s)",
                    (event.timestamp, event.device_id, event.sequence_number, event.temperature))
        else:
            event_id = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            cur.execute(f"INSERT INTO {table_name} (id, timestamp, device_id, sequence_number, temperature) VALUES (%s, %s, %s, %s, %s)",
                    (event_id, event.timestamp, event.device_id, event.sequence_number, event.temperature))
        count += 1
        if batch_mode and count >= batch_size:
            db.commit()
            count = 0
    if batch_mode:
        db.commit()
    cur.close()
    print("Finished inserting", flush=True)
