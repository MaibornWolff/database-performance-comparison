import os
import time
import requests
from modules import select_module
from modules.config import config
from modules.event_generator import generate_events


def worker_id():
    return os.environ.get("POD_NAME", "abcd")


def wait_for_collector_init():
    print("Waiting for collector", flush=True)
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    while True:
        try:
            response = requests.get(f"{url}/", timeout=2)
            if response.ok:
                print("Collector available. Starting work", flush=True)
                return
            else:
                #print(response, response.text, flush=True)
                pass
        except:
            pass
        time.sleep(2)


def report_results(ops, duration):
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    data = dict(worker=worker_id(), operations=ops, duration=duration)
    print(requests.post(f"{url}/result", json=data))


def run():
    print("Starting run", flush=True)
    mod = select_module()
    num_events = int(config["num_inserts"])
    events = generate_events(worker_id(), 0, num_events)
    wait_for_collector_init()
    time.sleep(2)
    start = time.time()
    mod.insert_events(events)
    duration = time.time() - start
    report_results(num_events, duration)
