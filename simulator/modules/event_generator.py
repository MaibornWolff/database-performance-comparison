from datetime import datetime
import random
from dataclasses import dataclass
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class Event:
    timestamp: int
    device_id: str
    sequence_number: str
    temperature: float


def generate_events(device_id, start_timestamp, num_events):
    if start_timestamp == 0:
        start_timestamp = int(datetime.now().timestamp()*1000)
    sequence_number = 1
    for i in range(num_events):
        event = Event(start_timestamp, device_id, sequence_number, random.uniform(-20, 35))
        yield event
        sequence_number += 1
        start_timestamp += random.randint(5, 10)*60
