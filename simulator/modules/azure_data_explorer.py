from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from azure.kusto.data.helpers import dataframe_from_result_table
from azure.kusto.data import DataFormat
from azure.kusto.ingest import QueuedIngestClient, IngestionProperties, FileDescriptor, BlobDescriptor, ReportLevel, \
    ReportMethod

# from .config import config TODO: uncomment

def test():

    KUSTO_URI = "https://kvc7rq22b9ye5d4a4fgyas.northeurope.kusto.windows.net"
    KUSTO_INGEST_URI = "https://ingest-kvc7rq22b9ye5d4a4fgyas.northeurope.kusto.windows.net"
    KUSTO_DATABASE = "ConnTest"

    KCSB_INGEST = KustoConnectionStringBuilder.with_interactive_login(KUSTO_INGEST_URI)
    KCSB_DATA = KustoConnectionStringBuilder.with_interactive_login(KUSTO_URI)

    DESTINATION_TABLE = "PopulationDataNew"
    DESTINATION_TABLE_COLUMN_MAPPING = "PopulationDataNew_CSV_Mapping"

    KUSTO_CLIENT = KustoClient(KCSB_DATA)
    CREATE_TABLE_COMMAND = ".create table PopulationDataNew (State: string, Population: int)"
    RESPONSE = KUSTO_CLIENT.execute_mgmt(KUSTO_DATABASE, CREATE_TABLE_COMMAND)
    # dataframe_from_result_table(RESPONSE.primary_results[0])

    CREATE_MAPPING_COMMAND = """.create table PopulationDataNew ingestion csv mapping 'PopulationDataNew_CSV_Mapping' '[{"Name":"State","datatype":"string","Ordinal":0}, {"Name":"Population","datatype":"int","Ordinal":1}]'"""
    KUSTO_CLIENT.execute_mgmt(KUSTO_DATABASE, CREATE_MAPPING_COMMAND)

    INGESTION_CLIENT = QueuedIngestClient(KCSB_INGEST)

    ingestion_props = IngestionProperties(
        database="ConnTest",
        table="PopulationDataNew",
        data_format=DataFormat.CSV
    )

    file_descriptor = FileDescriptor("modules/population.csv", 48)  # 3333 is the raw size of the data in bytes.
    result = INGESTION_CLIENT.ingest_from_file(file_descriptor, ingestion_props)
    print(repr(result))

    print('Done queuing up ingestion with Azure Data Explorer')


def _db():
    # cluster = Cluster()
    pass


def init():
    pass


def prefill_events(events):
    _insert_events(events, True, 1000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1000)
    _insert_events(events, batch_mode, batch_size)


def _insert_events(events, batch_mode, batch_size, use_values_lists=False):
    print("Connecting to database", flush=True)
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    print("Inserting events", flush=True)


def queries():
    db = _db()
