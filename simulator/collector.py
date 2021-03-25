from flask import Flask, request, jsonify
from modules import select_module
import time


app = Flask(__name__)
results = dict()


@app.route("/")
def index():
    return "Test Collector"


@app.route("/result", methods=["POST"])
def report_result():
    data = request.get_json()
    results[data["worker"]] = data
    return "OK"


@app.route("/report")
def collect_results():
    report = dict()
    report["workers"] = results
    sum_ops, sum_duration = 0, 0
    for worker in results.values():
        sum_ops = sum_ops + worker["operations"]
        sum_duration = sum_duration + worker["duration"]
    ops_per_second=sum_ops/(sum_duration/len(results))
    report["sum"] = dict(operations=sum_ops, duration=sum_duration, ops_per_second=ops_per_second)
    return jsonify(report)


def run():
    select_module().init()
    time.sleep(2)
    app.run(host='0.0.0.0', port=5000, debug=False)
