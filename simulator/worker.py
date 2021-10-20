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


def wait_for_prefill_complete():
    print("Waiting for prefill completion", flush=True)
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    while True:
        try:
            response = requests.get(f"{url}/prefill", timeout=2)
            if response.ok:
                print("Prefill complete. Starting work", flush=True)
                return
            else:
                pass
        except:
            pass
        time.sleep(4)


def do_prefill(mod):
    print("Doing prefill", flush=True)
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    num_events = int(config["prefill"]/int(os.environ["WORKER_COUNT"]))
    device_spread = int(config.get("device_spread", "1"))
    prefill_events = generate_events(worker_id(), 0, num_events, device_spread=device_spread)
    mod.prefill_events(prefill_events)
    requests.post(f"{url}/prefill", json=dict(worker=worker_id()))
    wait_for_prefill_complete()
    return num_events + 1


def run_queries(module):
    print("Running query task", flush=True)
    results = module.queries()
    print("Transmitting results")
    data = dict(worker=worker_id(), results=results)
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    print(requests.post(f"{url}/result", json=data))


def run_insert(module):
    print("Running insert task")
    if config["prefill"]:
        sequence_number = do_prefill(module)
    else:
        sequence_number = 1
    num_events = int(config["num_inserts"])
    device_spread = int(config.get("device_spread", "1"))
    events = generate_events(worker_id(), 0, num_events, sequence_number=sequence_number, device_spread=device_spread)
    time.sleep(2)
    start = time.time()
    module.insert_events(events)
    duration = time.time() - start
    url = os.environ.get("COLLECTOR_URL", "http://localhost:5000")
    data = dict(worker=worker_id(), operations=num_events, duration=duration)
    print(requests.post(f"{url}/result", json=data))


def run():
    print("Starting run", flush=True)
    module = select_module()
    wait_for_collector_init()
    task = config.get("task", "insert")
    if task == "query":
        run_queries(module)
    elif task == "insert":
        run_insert(module)
    else:
        raise Exception(f"Unknown task: {task}")
