import base64
import json
import os

print(os.getenv("RUN_CONFIG"))
print(base64.b64decode(os.getenv("RUN_CONFIG")))
config = json.loads(base64.b64decode(os.getenv("RUN_CONFIG")))
print(config)