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

print(AAD_APP_ID)
print(APP_KEY)
print(AUTHORITY_ID)

KUSTO_URI = config["kusto_uri"]
KUSTO_INGEST_URI = config["kusto_ingest_uri"]
KUSTO_DATABASE = config["kusto_db"]

print(KUSTO_URI)
print(KUSTO_INGEST_URI)
print(KUSTO_DATABASE)

def test():
    #     #interactive
    #     # kcsb_ingest = KustoConnectionStringBuilder.with_interactive_login(KUSTO_INGEST_URI)
    #     # kcsb_data = KustoConnectionStringBuilder.with_interactive_login(KUSTO_URI)
    #     #secure
    kcsb_ingest = KustoConnectionStringBuilder.with_aad_application_key_authentication("https://ingest-adxcompare.westeurope.kusto.windows.net", AAD_APP_ID, APP_KEY, AUTHORITY_ID)
    kcsb_data = KustoConnectionStringBuilder.with_aad_application_key_authentication("https://adxcompare.westeurope.kusto.windows.net", AAD_APP_ID, APP_KEY, AUTHORITY_ID)

    kusto_client = KustoClient(kcsb_data)
    create_table_command = f".create table PopulationTable (State: string, Population: int)"
    kusto_client.execute_mgmt("SampleDB", create_table_command)

    create_mapping_command = """.create table PopulationTable ingestion csv mapping 'PopulationDataNew_CSV_Mapping' '[{"Name":"State","datatype":"string","Ordinal":0}, {"Name":"Population","datatype":"int","Ordinal":1}]'"""
    kusto_client.execute_mgmt("SampleDB", create_mapping_command)

    ingestion_client = QueuedIngestClient(kcsb_ingest)
    ingestion_props = IngestionProperties(database="SampleDB", table="PopulationTable", data_format=DataFormat.CSV,
                                          ignore_first_record=True)
    mapping = {'State': ['Texas', 'New York', 'Arizona'], 'Population': [300, 400, 500]}
    dataframe = pd.DataFrame(data=mapping)
    ingestion_result = ingestion_client.ingest_from_dataframe(dataframe, ingestion_props)
    print('Done queuing up ingestion with Azure Data Explorer')
    print(f"Ingestion_result: {ingestion_result}")
# import time
# time.sleep(50)
# sample_query = "PopulationDataNew | summarize max(Population), min(Population), avg(Population) by State"
# sample_response = kusto_client.execute("ConnTest", sample_query)
# for row in sample_response.primary_results[0]:
#     # printing specific columns by index
#     print("value at 0 {}".format(row[0]))
#     print("\n")
#     # printing specific columns by name
#     print("EventType:{}".format(row["State"]))
#     print("EventType:{}".format(row["max_Population"]))
#     print("EventType:{}".format(row["min_Population"]))
#     print("EventType:{}".format(row["avg_Population"]))
# try:
#     delete_table_command = f".drop table PopulationDataNew2"
#     kusto_client.execute_mgmt(KUSTO_DATABASE, delete_table_command)
# except KustoApiError:
#     print("Could not delete table. Table was probably not found")
# delete_table_command = f".drop table PopulationDataNew"
# kusto_client.execute_mgmt(KUSTO_DATABASE, delete_table_command)




#
#
# DESTINATION_TABLE = "PopulationDataNew"
# DESTINATION_TABLE_COLUMN_MAPPING = "PopulationDataNew_CSV_Mapping"



def _ingestion_client():
    kcsb_ingest = KustoConnectionStringBuilder.with_aad_application_key_authentication(KUSTO_INGEST_URI, AAD_APP_ID, APP_KEY, AUTHORITY_ID)
    return QueuedIngestClient(kcsb_ingest)


def _kusto_client():
    kcsb_data = KustoConnectionStringBuilder.with_aad_application_key_authentication(KUSTO_URI, AAD_APP_ID, APP_KEY, AUTHORITY_ID)
    return KustoClient(kcsb_data)


def init():
    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]
    with _kusto_client() as kusto_client:
        response = kusto_client.execute(KUSTO_DATABASE, f""".show tables | where DatabaseName == "{KUSTO_DATABASE}" """)
        existing_tables = [row[0] for row in response.primary_results[0]]
        print(f"Following tables already exist: {existing_tables}")
        if config["clean_database"]:
            for table_name in existing_tables:
                try:
                    print(f"Delete table {table_name}")
                    delete_table_command = f".drop table {table_name}"
                    kusto_client.execute_mgmt(KUSTO_DATABASE, delete_table_command)
                except KustoApiError as error:
                    print(f"Could not delete table, due to:\n {error}")
        else:
            table_names = [table_name for table_name in table_names if table_name not in existing_tables]
        for table_name in table_names:
            print(f"Create table {table_name}")
            create_table_command = f".create table {table_name} (timestamp: long, device_id: string, sequence_number: long, temperature: real)"
            kusto_client.execute_mgmt(KUSTO_DATABASE, create_table_command)

            if not config.get("batch_mode", True):
                print(f"Enable streaming for {table_name}")
                enable_streaming_command = f".alter table {table_name} policy streamingingestion enable"
                kusto_client.execute_mgmt(KUSTO_DATABASE, enable_streaming_command)
                # Manuel check: .show table <table-name> policy streamingingestion

            create_mapping_command = f""".create table {table_name} ingestion csv mapping '{table_name}_CSV_Mapping' '[{{"Name":"timestamp","datatype":"long","Ordinal":0}}, {{"Name":"device_id","datatype":"string","Ordinal":1}}, {{"Name":"sequence_number","datatype":"long","Ordinal":2}}, {{"Name":"temperature","datatype":"real","Ordinal":3}}]'"""
            kusto_client.execute_mgmt(KUSTO_DATABASE, create_mapping_command)


def prefill_events(events):
    _insert_events(events, True, 1_000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1_000)
    _insert_events(events, batch_mode, batch_size)


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
            table = table_names[int(idx / batch_size) % len(table_names)]
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


def _stream_insert(events, table_names):
    number_of_tables = len(table_names)
    number_of_inserts = int(config["num_inserts"])
    inserts_per_table = number_of_inserts // number_of_tables
    print("Stream ingestion", flush=True)
    with _ingestion_client() as ingestion_client:
        for table in table_names:
            print(f"Ingest {inserts_per_table} into {table}", flush=True)
            events_partition = list(itertools.islice(events, inserts_per_table))
            event = events_partition[0]
            byte_seq = event.to_json()
            bytes_array = byte_seq.encode("utf-8")
            byte_stream = io.BytesIO(bytes_array)
            stream_descriptor = StreamDescriptor(byte_stream)
            ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table, data_format=DataFormat.JSON)
            result = ingestion_client.ingest_from_stream(stream_descriptor, ingestion_props)
            print(result)

            # for dix, event in enumerate(events_partition):
            #     print(f"Event {dix}", flush=True)
            #     bytes_sequence = pickle.dumps(event)
            #     bytes_stream = io.BytesIO(bytes_sequence)
            #     stream_descriptor = StreamDescriptor(bytes_stream)
            #     print(StreamDescriptor.get_instance(stream_descriptor).stream)
            #     ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table, data_format=DataFormat.CSV)
            #     ingestion_client.ingest_from_stream(stream_descriptor, ingestion_props)

            # buffered_io = io.BytesIO()
            # for event in itertools.islice(events, inserts_per_table):
            #     buffered_io.write(json.dumps(event.__dict__).encode('utf-8'))
            # # (buffered_io.write(json.dumps(event.__dict__).encode('utf-8')) for event in itertools.islice(events, inserts_per_table))
            # print(f"Ingest {inserts_per_table} into {table}")
            # print(f"Bytes: {buffered_io.getbuffer().nbytes}")
            # ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table,
            #                                       ignore_first_record=False)
            # result = ingestion_client.ingest_from_stream(buffered_io, ingestion_props)
            # print(result)


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


_queries = {
    "count-events": "events | count",
    "temperature-min-max": "events| summarize max(temperature), min(temperature)",
    "temperature-stats": "events| summarize max(temperature), avg(temperature), min(temperature)",
    "temperature-stats-per-device": "events | summarize max(temperature), avg(temperature), min(temperature) by device_id",
    "newest-per-device": "events | partition by device_id (top 1 by timestamp desc | project device_id, temperature)",
}


def queries():
    if "queries" in config:
        included = config["queries"].split(",")
        for key in list(_queries.keys()):
            if key not in included:
                del _queries[key]
    print(_queries)
    query_times = dict([(name, []) for name in _queries.keys()])
    for _ in range(0, int(config["runs"])):
        for name, query in _queries.items():
            with _kusto_client() as kusto_client:
                print(f"Executing query {name}", flush=True)
                start = time.time()
                result = kusto_client.execute(KUSTO_DATABASE, query)
                print(result)
                duration = time.time() - start
                print(f"Finished query. Duration: {duration}", flush=True)
                query_times[name].append(duration)

    return query_times
