import psycopg2
from .config import config


def _db():
    connection_string = config["connection_string"]
    con = psycopg2.connect(connection_string)
    con.set_session(autocommit=True)
    return con


def init():
    db = _db()
    cur = db.cursor()
    
    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    for table_name in ["events0", "events1", "events2", "events3", "events"]:
        cur.execute(f"""DROP TABLE IF EXISTS {table_name}""")

    pk_column = "serial" if config["primary_key"] == "db" else "varchar"

    for table_name in table_names:
        cur.execute(
        f"""
        CREATE TABLE {table_name} (id {pk_column} PRIMARY KEY,
            timestamp bigint,
            device_id varchar,
            sequence_number bigint,
            temperature real
            )
        """)
    print("Created table events")
    cur.close()


def insert_events(events):
    print("Connecting to database", flush=True)
    db = _db()
    print("Inserting events", flush=True)
    for idx, event in enumerate(events):
        if config["use_multiple_tables"]:
            table_name = f"events{idx%4}"
        else:
            table_name = "events"
        cur = db.cursor()
        if config["primary_key"] == "db":
            cur.execute(f"INSERT INTO {table_name} (timestamp, device_id, sequence_number, temperature) VALUES (%s, %s, %s, %s)",
                    (event.timestamp, event.device_id, event.sequence_number, event.temperature))
        else:
            event_id = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            cur.execute(f"INSERT INTO {table_name} (id, timestamp, device_id, sequence_number, temperature) VALUES (%s, %s, %s, %s, %s)",
                    (event_id, event.timestamp, event.device_id, event.sequence_number, event.temperature))
        cur.close()
    print("Finished inserting", flush=True)
