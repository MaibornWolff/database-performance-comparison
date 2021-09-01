import psycopg2
import psycopg2.extras
from .config import config

import io


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
    # "primary_key" can be "client" to generate the PK value from the application, or "db" to use the "serial"
    #  or "sql" for the SQL standard generated column, and then the cache size is the batch size
    if config["primary_key"] == "sql":
     pk_column = f'bigint generated always as identity ( start with 1 cache {config.get("batch_size", 100)} )'
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
    db = _db()
    cur = db.cursor()

    print("Inserting events", flush=True)

    if use_values_lists and batch_mode:
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
                for table_index, values in enumerate(values_lists):
                    if config["primary_key"] != "client":
                        psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (timestamp, device_id, sequence_number, temperature) VALUES %s", values)
                    else:
                        psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (id, timestamp, device_id, sequence_number, temperature) VALUES %s", values)
                    values.clear()
                db.commit()
                count = 0
        if count > 0:
            for table_index, values in enumerate(values_lists):
                if config["primary_key"] != "client":
                    psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (timestamp, device_id, sequence_number, temperature) VALUES %s", values)
                else:
                    psycopg2.extras.execute_values(cur, f"INSERT INTO {table_names[table_index]} (id, timestamp, device_id, sequence_number, temperature) VALUES %s", values)
            db.commit()
    elif not(use_values_lists) and batch_mode: # This uses the COPY mode of Postgres, when in batch without a VALUES list
        count = 0
        # the values_lists here is a StringIO containing the TSV to COPY
        # TODO: check from pg_settings where name='yb_default_copy_from_rows_per_transaction' so that all can be run in one call on YugabyteDB
        values_lists = [io.StringIO() for _ in range(4 if use_multiple_tables else 1)]
        for idx, event in enumerate(events):
            if config["primary_key"] != "client": #franck#
                val = f'{event.timestamp}\t{event.device_id}\t{event.sequence_number}\t{event.temperature}\n' #franck#
            else:
                event_id = f"{event.device_id}{event.timestamp}{event.sequence_number}"
                val = f'{event_id}\t{event.timestamp}\t{event.device_id}\t{event.sequence_number}\t{event.temperature}\n' #franck#
            if use_multiple_tables:
                values_lists[idx%4].writelines(val)
            else:
                values_lists[0].writelines(val)
            count += 1
            if count >= batch_size:
                for table_index, values in enumerate(values_lists):
                    values.seek(0)
                    if config["primary_key"] != "client": #franck#
                        cur.copy_from(values,table_names[table_index],sep="\t",columns=('timestamp', 'device_id', 'sequence_number', 'temperature'))
                    else:
                        cur.copy_from(values,table_names[table_index],sep="\t",columns=('id','timestamp', 'device_id', 'sequence_number', 'temperature'))
                    values.seek(0)
                    values.truncate(0)
                db.commit()
                count = 0
        if count > 0:
                for table_index, values in enumerate(values_lists):
                    values.seek(0)
                    if config["primary_key"] != "client": #franck#
                        cur.copy_from(values,table_names[table_index],sep="\t",columns=('timestamp', 'device_id', 'sequence_number', 'temperature'))                   
                    else:
                        cur.copy_from(values,table_names[table_index],sep="\t",columns=('id','timestamp', 'device_id', 'sequence_number', 'temperature'))
                db.commit()    
    else:
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
    print("Finished inserting", flush=True)
