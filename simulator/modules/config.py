import base64
import json
import os


config = json.loads(base64.b64decode(os.getenv("RUN_CONFIG")))
