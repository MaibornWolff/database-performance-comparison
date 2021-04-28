from datetime import datetime
import random
import string
from dataclasses import dataclass
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class Event:
    timestamp: int
    device_id: str
    sequence_number: str
    temperature: float


def _rand_string(length):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_events(device_id, start_timestamp, num_events, sequence_number=1, device_spread=1):
    device_ids = [f"{_rand_string(4)}{device_id}{_rand_string(4)}" for i in range(device_spread)]
    if start_timestamp == 0:
        start_timestamp = int(datetime.now().timestamp()*1000)
    for i in range(num_events):
        event = Event(start_timestamp, device_ids[i%device_spread], sequence_number, random.uniform(-20, 35))
        yield event
        sequence_number += 1
        start_timestamp += random.randint(5, 10)*60
