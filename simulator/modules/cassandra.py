import queue
from queue import Queue
import cassandra
from cassandra.query import BatchStatement, BatchType, BoundStatement, SimpleStatement
from cassandra.cluster import Cluster, ConsistencyLevel
from .config import config

KEYSPACE = config["keyspace"]
def _db():
    cluster = Cluster(contact_points=config["contact_points"].split(","))
    session = cluster.connect()
    return session


def prefill_events(events):
    _insert_events(events, True, 1000)


def init():
    session: cassandra.cluster.Session = _db()
    session.execute(f"""DROP KEYSPACE IF EXISTS {KEYSPACE}""")
    session.execute(f"""CREATE KEYSPACE IF NOT EXISTS {KEYSPACE}
        WITH replication = {{ 'class': 'SimpleStrategy', 'replication_factor':{config["replication_factor"]}}}
        """)

    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    for table_name in ["events0", "events1", "events2", "events3", "events"]:
        session.execute(f"""DROP TABLE IF EXISTS {KEYSPACE}.{table_name}""")

    for table_name in table_names:
        session.execute(
            f"""CREATE TABLE {KEYSPACE}.{table_name} (
            timestamp bigint,
            device_id varchar,
            sequence_number bigint,
            temperature float,
            PRIMARY KEY (device_id, sequence_number)
            )
        """)
    print("Created table events")

def prefill_events(events):
    _insert_events(events, True, 1000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1000)
    _insert_events(events, batch_mode, batch_size)

def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]
    session = _db()
    session.default_timeout = 60
    statements_list = [session.prepare(f"INSERT INTO {KEYSPACE}.{table_name} (timestamp, device_id, sequence_number, temperature) VALUES (?, ?, ?, ?)") for table_name in table_names]
    max_sync_calls = config["max_sync_calls"]

    print("Inserting events", flush=True)
    if max_sync_calls > 1:
        futures = Queue(maxsize=max_sync_calls+1)
        for idx, stmt in enumerate(_generate_statements(events, statements_list, len(table_names), batch_mode, batch_size)):
            if idx >= max_sync_calls:
                futures.get_nowait().result()
            future = session.execute_async(stmt)
            futures.put_nowait(future)
        while True:
            try:
                futures.get_nowait().result()
            except queue.Empty:
                break
    else:
        for stmt in _generate_statements(events, statements_list, len(table_names), batch_mode, batch_size):
            session.execute(stmt)
    session.shutdown()
    print("Finished inserting", flush=True)

def _generate_statements(events, statements_list, number_of_tables, batch_mode, batch_size = 1):
    if not batch_mode:
        for idx, event in enumerate(events):
            yield statements_list[idx%number_of_tables].bind((event.timestamp, event.device_id, event.sequence_number, event.temperature))
    else:
        for idx, batch in enumerate(_batch_events(events, batch_size)):
            batch_statement = BatchStatement(batch_type=BatchType.UNLOGGED, consistency_level=ConsistencyLevel.name_to_value[config["consistency_level"]])
            for event in batch:
                batch_statement.add(statements_list[idx%number_of_tables].bind((event.timestamp, event.device_id, event.sequence_number, event.temperature)))
            yield batch_statement

def _batch_events(events, batch_size):
    values = []
    for event in events:
        values.append(event)
        if len(values) >= batch_size:
            yield values
            values = []
    if values:
        yield values
