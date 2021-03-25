
def select_module():
    import os
    mod = os.environ.get("TEST_MODULE")
    if mod == "postgres":
        from . import postgres
        return postgres
    elif mod == "arangodb":
        from . import arangodb
        return arangodb
    else:
        raise Exception(f"Unknown module: {mod}")
