
def select_module():
    import os
    mod = os.environ.get("TEST_MODULE")
    if mod == "postgres":
        from . import postgres
        return postgres
    elif mod == "arangodb":
        from . import arangodb
        return arangodb
    elif mod == "cassandra":
        from . import cassandra
        return cassandra
    elif mod == "influxdb":
        from . import influxdb
        return influxdb
    elif mod == "timescaledb":
        from . import timescaledb
        return timescaledb
    elif mod == "elasticsearch":
        from . import elasticsearch
        return elasticsearch
    elif mod == "azure_data_explorer":
        from . import azure_data_explorer
        return azure_data_explorer
    else:
        raise Exception(f"Unknown module: {mod}")
