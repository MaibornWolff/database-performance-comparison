import base64
import json
import click
import yaml
from .run import one_run
from . import commands


@commands.command()
@click.option('-t', '--target', required=True, help="Name of the target")
@click.option('-c', '--config', default="config.yaml", help="Name of the config file to use")
@click.option('-w', '--workers', default=1, help="Number of workers to use")
@click.option('-r', '--runs', default=3, help='Number of times each query should be executed, default=3')
@click.option("--extra-option", multiple=True, help="Extra options for the database module")
@click.option("--timeout", default=0, help="Timeout in seconds to wait for one run to complete. Increase this if you use higher number of inserts, or set to 0 to disable timeout. default=0")
def query(target, config, workers, runs, extra_option, timeout):
    config = _read_config(config)
    target_config = config["targets"][target]
    namespace = config.get("namespace", "default")
    run_config, target_module = _prepare_run_config(target_config, runs, extra_option)
    results = one_run(workers, run_config, target_module, timeout, namespace, endpoint="/report/queries")
    max_name_len = max([len(name) for name in results["queries"].keys()])
    spacing = " " * (max_name_len - len("Query"))
    print(f"Query{spacing}\tMin  \tMax  \tAvg")
    for name, stats in results["queries"].items():
        spacing = " " * (max_name_len - len(name))
        result_min = round(stats['min'], 2)
        result_max = round(stats['max'], 2)
        result_avg = round(stats['avg'], 2)
        print(f"{name}{spacing}\t{result_min:>5.2f}\t{result_max:>5.2f}\t{result_avg:>5.2f}")

def _prepare_run_config(target_config, runs, extra_options):
    config = target_config
    config.update({
        "task": "query",
        "runs": runs,
    })
    for option in extra_options:
        k, v = option.split("=", 1)
        config[k] = v
    return base64.b64encode(json.dumps(config).encode("utf-8")).decode("utf-8"), config["module"]
    

def _read_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config
