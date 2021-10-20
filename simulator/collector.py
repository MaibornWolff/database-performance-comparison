import os
import time
from flask import Flask, request, jsonify, make_response
from modules import select_module
from modules.config import config


app = Flask(__name__)
results = dict()
prefill = list()
WORKER_COUNT = int(os.environ["WORKER_COUNT"])


@app.route("/")
def index():
    return "Test Collector"


@app.route("/prefill", methods=["POST"])
def report_prefill():
    data = request.get_json()
    prefill.append(data["worker"])
    return "OK"


@app.route("/prefill", methods=["GET"])
def prefill_status():
    if len(prefill) >= WORKER_COUNT:
        return make_response("OK", 200)
    else:
        return make_response("waiting on workers", 503)


@app.route("/result", methods=["POST"])
def report_result():
    data = request.get_json()
    results[data["worker"]] = data
    return "OK"


@app.route("/report/insert")
def collect_results_insert():
    report = dict()
    report["workers"] = results
    sum_ops, sum_duration = 0, 0
    for worker in results.values():
        sum_ops = sum_ops + worker["operations"]
        sum_duration = sum_duration + worker["duration"]
    ops_per_second=sum_ops/(sum_duration/len(results))
    report["sum"] = dict(operations=sum_ops, duration=sum_duration, ops_per_second=ops_per_second)
    return jsonify(report)


@app.route("/report/queries")
def collect_results_queries():
    report = dict()
    queries = dict([(name, []) for name in list(results.values())[0]["results"].keys()])
    report["workers"] = results
    report["queries"] = dict()
    
    for worker in results.values():
        for name, values in worker["results"].items():
            queries[name].extend(values)

    for name, values in queries.items():
        report["queries"][name] = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values)/len(values),
        }
    
    return jsonify(report)

def run():
    module = select_module()
    if config.get("task", "insert") == "insert":
        module.init()
    # It looks like in some cases for yugabytedb the created table is not instantly available for all workers so wait a few seconds
    time.sleep(10) 
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=False)
