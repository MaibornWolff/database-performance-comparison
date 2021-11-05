
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
    else:
        raise Exception(f"Unknown module: {mod}")
