import io
import itertools
import os
import time

import pandas as pd
from azure.kusto.data import DataFormat
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoApiError
from azure.kusto.ingest import QueuedIngestClient, IngestionProperties, StreamDescriptor

from .config import config

AAD_APP_ID = os.getenv("adx_aad_app_id")
APP_KEY = os.getenv("adx_app_key")
AUTHORITY_ID = os.getenv("adx_authority_id")

KUSTO_URI = config["kusto_uri"]
KUSTO_INGEST_URI = config["kusto_ingest_uri"]
KUSTO_DATABASE = config["kusto_db"]


def init():
    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]
    with _kusto_client() as kusto_client:
        existing_tables = _get_existing_tables(kusto_client)
        if config["clean_database"]:
            _clean_database(existing_tables, kusto_client)
        else:
            table_names = _get_tables_requiring_creation(existing_tables, table_names)
        for table_name in table_names:
            _create_table(kusto_client, table_name)
            _handle_stream_ingestion(kusto_client, table_name)
            _create_ingestion_mapping(kusto_client, table_name)


def prefill_events(events):
    _insert_events(events, True, 1_000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1_000)
    _insert_events(events, batch_mode, batch_size)


_queries = {
    "count-events": "events | count",
    "temperature-min-max": "events| summarize max(temperature), min(temperature)",
    "temperature-stats": "events| summarize max(temperature), avg(temperature), min(temperature)",
    "temperature-stats-per-device": "events | summarize max(temperature), avg(temperature), min(temperature) by device_id",
    "newest-per-device": "events | partition by device_id (top 1 by timestamp desc | project device_id, temperature)",
}


def queries():
    _filter_queries_to_execute()
    query_times = dict([(name, []) for name in _queries.keys()])
    for _ in range(0, int(config["runs"])):
        for name, query in _queries.items():
            _execute_query(name, query, query_times)
    return query_times


def _ingestion_client():
    kcsb_ingest = KustoConnectionStringBuilder.with_aad_application_key_authentication(KUSTO_INGEST_URI, AAD_APP_ID, APP_KEY, AUTHORITY_ID)
    return QueuedIngestClient(kcsb_ingest)


def _kusto_client():
    kcsb_data = KustoConnectionStringBuilder.with_aad_application_key_authentication(KUSTO_URI, AAD_APP_ID, APP_KEY, AUTHORITY_ID)
    return KustoClient(kcsb_data)


def _get_tables_requiring_creation(existing_tables, table_names):
    return [table_name for table_name in table_names if table_name not in existing_tables]


def _clean_database(existing_tables, kusto_client):
    for table_name in existing_tables:
        try:
            print(f"Delete table {table_name}")
            delete_table_command = f".drop table {table_name}"
            kusto_client.execute_mgmt(KUSTO_DATABASE, delete_table_command)
        except KustoApiError as error:
            print(f"Could not delete table, due to:\n {error}")


def _get_existing_tables(kusto_client):
    response = kusto_client.execute(KUSTO_DATABASE, f""".show tables | where DatabaseName == "{KUSTO_DATABASE}" """)
    existing_tables = [row[0] for row in response.primary_results[0]]
    print(f"Following tables already exist: {existing_tables}")
    return existing_tables


def _create_ingestion_mapping(kusto_client, table_name):
    create_mapping_command = f""".create table {table_name} ingestion csv mapping '{table_name}_CSV_Mapping' '[{{"Name":"timestamp","datatype":"long","Ordinal":0}}, {{"Name":"device_id","datatype":"string","Ordinal":1}}, {{"Name":"sequence_number","datatype":"long","Ordinal":2}}, {{"Name":"temperature","datatype":"real","Ordinal":3}}]'"""
    kusto_client.execute_mgmt(KUSTO_DATABASE, create_mapping_command)


def _create_table(kusto_client, table_name):
    print(f"Create table {table_name}")
    create_table_command = f".create table {table_name} (timestamp: long, device_id: string, sequence_number: long, temperature: real)"
    kusto_client.execute_mgmt(KUSTO_DATABASE, create_table_command)


def _handle_stream_ingestion(kusto_client, table_name):
    if not config.get("batch_mode", True):
        print(f"Enable streaming for {table_name}")
        enable_streaming_command = f".alter table {table_name} policy streamingingestion enable"
        kusto_client.execute_mgmt(KUSTO_DATABASE, enable_streaming_command)
        # Manuel check: .show table <table-name> policy streamingingestion


def _batch_insert(events, batch_size, table_names):
    count = 0
    timestamps = []
    device_ids = []
    sequence_numbers = []
    temperatures = []
    for idx, event in enumerate(events):
        timestamps.append(event.timestamp)
        device_ids.append(event.device_id)
        sequence_numbers.append(event.sequence_number)
        temperatures.append(event.temperature)
        count += 1
        if count >= batch_size:
            table = _determine_table_for_ingestion(batch_size, idx, table_names)
            print(f"Insert {count} entries into {table}")
            _ingest(table, timestamps, device_ids, sequence_numbers, temperatures)
            timestamps.clear()
            device_ids.clear()
            sequence_numbers.clear()
            temperatures.clear()
            count = 0
    if count > 0:
        print(f"Insert {count} entries into {table_names[0]}")
        _ingest(table_names[0], timestamps, device_ids, sequence_numbers, temperatures)


def _determine_table_for_ingestion(batch_size, idx, table_names):
    return table_names[int(idx / batch_size) % len(table_names)]


def _stream_insert(events, table_names):
    number_of_tables = len(table_names)
    number_of_inserts = int(config["num_inserts"])
    inserts_per_table = number_of_inserts // number_of_tables
    print("Stream ingestion", flush=True)
    with _ingestion_client() as ingestion_client:
        for table in table_names:
            _ingest_by_stream(events, ingestion_client, inserts_per_table, table)


def _ingest_by_stream(events, ingestion_client, inserts_per_table, table):
    print(f"Ingest {inserts_per_table} into {table}", flush=True)
    events_partition = list(itertools.islice(events, inserts_per_table))
    json_string = _to_json(events_partition)
    stream_descriptor = _create_stream_descriptor(json_string)
    ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table,
                                          data_format=DataFormat.SINGLEJSON)
    result = ingestion_client.ingest_from_stream(stream_descriptor, ingestion_props)
    print(result)


def _create_stream_descriptor(json_string):
    bytes_array = json_string.encode("utf-8")
    byte_stream = io.BytesIO(bytes_array)
    byte_stream.flush()
    stream_descriptor = StreamDescriptor(byte_stream)
    return stream_descriptor


def _to_json(events_partition):
    json_string = ""
    for event in events_partition:
        json_string = json_string + event.to_json() + "\n"
    return json_string


def _ingest(table, timestamps, device_ids, sequence_numbers, temperatures):
    with _ingestion_client() as ingestion_client:
        ingestion_data = {'timestamp': timestamps, 'device_id': device_ids, 'sequence_number': sequence_numbers,
                          'temperature': temperatures}
        dataframe = pd.DataFrame(data=ingestion_data)
        ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table, data_format=DataFormat.CSV,
                                              ignore_first_record=True)
        result = ingestion_client.ingest_from_dataframe(dataframe, ingestion_props)
        print(result)


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    print("Inserting events", flush=True)
    if batch_mode:
        _batch_insert(events, batch_size, table_names)
    else:
        _stream_insert(events, table_names)


def _execute_query(name, query, query_times):
    with _kusto_client() as kusto_client:
        print(f"Executing query {name}", flush=True)
        start = time.time()
        kusto_client.execute(KUSTO_DATABASE, query)
        duration = time.time() - start
        print(f"Finished query. Duration: {duration}", flush=True)
        query_times[name].append(duration)


def _filter_queries_to_execute():
    if "queries" in config:
        included = config["queries"].split(",")
        for key in list(_queries.keys()):
            if key not in included:
                del _queries[key]
    print(_queries)
