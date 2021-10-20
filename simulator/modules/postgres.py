import io
import time
import psycopg2
import psycopg2.extras
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

    if "install_extensions" in config:
        for extension in config["install_extensions"].split(","):
            cur.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
        db.commit()

    # See README for explanation of the different modes
    if config["primary_key"] == "sql":
        pk_column = f'bigint generated always as identity ( start with 1 cache {config.get("batch_size", 100)} )'
    elif config["primary_key"] == "uuid":
        pk_column = 'uuid not null default gen_random_uuid()'
    elif config["primary_key"] == "db":
        pk_column = "serial"
    else:
        pk_column = "varchar" 

    for table_name in table_names:
        cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (id {pk_column} ,
            timestamp bigint,
            device_id varchar,
            sequence_number bigint,
            temperature real,
            {config.get("primary_key_constraint","PRIMARY KEY (id)")}
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
    use_values_lists = config.get("use_values_lists", "false").lower() == "true"
    _insert_events(events, batch_mode, batch_size, use_values_lists)


def _insert_events(events, batch_mode, batch_size, use_values_lists=False):
    print("Connecting to database", flush=True)
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    print("Inserting events", flush=True)

    if use_values_lists and batch_mode:
        _values_lists_mode(events, use_multiple_tables, batch_size, table_names)
    elif not use_values_lists and batch_mode: # This uses the COPY mode of Postgres, when in batch without a VALUES list
        _copy_mode(events, use_multiple_tables, batch_size, table_names)
    else:
        _single_insert_mode(events, use_multiple_tables, batch_size, batch_mode)

    print("Finished inserting", flush=True)


def _values_lists_mode(events, use_multiple_tables, batch_size, table_names):
    db = _db()
    cur = db.cursor()
    count = 0
    values_lists = [list() for _ in range(4 if use_multiple_tables else 1)]
    for idx, event in enumerate(events):
        if config["primary_key"] != "client":
            val = (event.timestamp, event.device_id, event.sequence_number, event.temperature)
        else:
            event_id = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            val = (event_id, event.timestamp, event.device_id, event.sequence_number, event.temperature)
        if use_multiple_tables:
            values_lists[idx%4].append(val)
        else:
            values_lists[0].append(val)
        count += 1
        if count >= batch_size:
            _values_lists_insert(db, cur, values_lists, table_names)
            count = 0
    if count > 0:
        _values_lists_insert(db, cur, values_lists, table_names)
    cur.close()


def _values_lists_insert(db, cur, values_lists, table_names):
    # Implement retry due to TransactionAbortedError(ABORT_REASON_NEW_LEASE_PREVENTS_TXN) problems with CockroachDB
    done = False
    for _ in range(5):
        try:
            for table_index, values in enumerate(values_lists):
                if config["primary_key"] != "client":
                    psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (timestamp, device_id, sequence_number, temperature) VALUES %s", values)
                else:
                    psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (id, timestamp, device_id, sequence_number, temperature) VALUES %s", values)
            db.commit()
            done = True
            break
        except:
            print("Retrying insert due to problem")
    if not done:
        raise Exception("Failed to insert data after 5 tries. Aborting")
    for values in values_lists:
        values.clear()


def _copy_mode(events, use_multiple_tables, batch_size, table_names):
    db = _db()
    cur = db.cursor()
    count = 0
    # the values_lists here is a StringIO containing the TSV to COPY
    values_lists = [io.StringIO() for _ in range(4 if use_multiple_tables else 1)]
    for idx, event in enumerate(events):
        if config["primary_key"] != "client": 
            val = f'{event.timestamp}\t{event.device_id}\t{event.sequence_number}\t{event.temperature}\n' 
        else:
            event_id = f"{event.device_id}{event.timestamp}{event.sequence_number}"
            val = f'{event_id}\t{event.timestamp}\t{event.device_id}\t{event.sequence_number}\t{event.temperature}\n' 
        if use_multiple_tables:
            values_lists[idx%4].writelines(val)
        else:
            values_lists[0].writelines(val)
        count += 1
        if count >= batch_size:
            for table_index, values in enumerate(values_lists):
                values.seek(0)
                if config["primary_key"] != "client": 
                    cur.copy_from(values,table_names[table_index],sep="\t",columns=('timestamp', 'device_id', 'sequence_number', 'temperature'))
                else:
                    cur.copy_from(values,table_names[table_index],sep="\t",columns=('id','timestamp', 'device_id', 'sequence_number', 'temperature'))
                values.seek(0)
                values.truncate(0)
            db.commit()
            count = 0
    # Commit any remaining data
    if count > 0:
        for table_index, values in enumerate(values_lists):
            values.seek(0)
            if config["primary_key"] != "client": 
                cur.copy_from(values,table_names[table_index],sep="\t",columns=('timestamp', 'device_id', 'sequence_number', 'temperature'))                   
            else:
                cur.copy_from(values,table_names[table_index],sep="\t",columns=('id','timestamp', 'device_id', 'sequence_number', 'temperature'))
        db.commit()
    cur.close()


def _single_insert_mode(events, use_multiple_tables, batch_size, batch_mode):
    db = _db()
    cur = db.cursor()
    count = 0
    for idx, event in enumerate(events):
        if use_multiple_tables:
            table_name = f"events{idx%4}"
        else:
            table_name = "events"

        if config["primary_key"] != "client":
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


_indices = [
    "CREATE INDEX IF NOT EXISTS events_device_ts ON events (device_id, timestamp ASC)",
    "CREATE INDEX IF NOT EXISTS events_temp ON events (temperature ASC)",
]

_queries = {
    "count-events": "SELECT count(*) FROM events",
    "temperature-min-max": "SELECT max(temperature), min(temperature) FROM events",
    "temperature-stats": "SELECT max(temperature), avg(temperature), min(temperature) FROM events",
    "temperature-stats-per-device": "SELECT device_id, max(temperature), avg(temperature), min(temperature) FROM events GROUP BY device_id",
    "newest-per-device": "SELECT e.device_id, e.temperature FROM events e JOIN (SELECT device_id, max(timestamp) as ts FROM events GROUP BY device_id) newest ON e.device_id=newest.device_id AND e.timestamp = newest.ts",
}

def queries():
    db = _db()
    cur = db.cursor()
    if config.get("create_indices", "false").lower() == "true":
        for index in _indices:
            cur.execute(index)
        db.commit()

    query_times = dict([(name, []) for name in _queries.keys()])
    for i in range(int(config["runs"])):
        for name, query in _queries.items():
            start = time.time()
            cur.execute(query)
            list(cur.fetchall()) # Force client to actually fetch results
            duration = time.time() - start
            query_times[name].append(duration)

    return query_times
