import base64
import json
import sys
import click
import yaml
from . import commands
from .run import one_run



@commands.command()
@click.option('-t', '--target', required=True, help="Name of the target")
@click.option('-c', '--config', default="config.yaml", help="Name of the config file to use")
@click.option('-w', '--workers', default="1,4,8,12,16", help="Sets of worker counts to use, separate by comma without space, default='1,4,8,12,16'")
@click.option('-r', '--runs', default=3, help='Number of runs per worker count, default=3')
@click.option("--primary-key", default="db", type=click.Choice(['sql', 'db', 'client', 'uuid'], case_sensitive=False))
@click.option("--tables", default="single", type=click.Choice(['single', 'multiple'], case_sensitive=False))
@click.option("--num-inserts", default=10000, help="Number of inserts per worker, default=10000")
@click.option("--prefill", default=0, help="Insert this number of events into the table before starting the test run, default=0")
@click.option("--extra-option", multiple=True, help="Extra options for the database module")
@click.option("--timeout", default=0, help="Timeout in seconds to wait for one run to complete. Increase this if you use higher number of inserts, or set to 0 to disable timeout. default=0")
@click.option("--batch", default=0, help="Number of events to insert in one batch, default 0 disables batch mode")
@click.option('--clean/--no-clean', default=True, help="Clean up the database before each run, enabled by default")
@click.option('--steps', default=0, help="TODO")
def insert(target, config, workers, runs, primary_key, tables, num_inserts, prefill, extra_option, timeout, batch, clean, steps):
    worker_counts = list(map(lambda el: int(el), workers.split(",")))
    config = _read_config(config)
    target_config = config["targets"][target]
    namespace = config.get("namespace", "default")
    if steps and len(worker_counts) > 1:
        print("ERROR: If using the --steps option only one worker count can be used")
        sys.exit(1)
    if steps and runs > 1:
        print("ERROR: If using the --steps option only one run is allowed")
        sys.exit(1)
    if steps and prefill:
        print("ERROR: --steps and --prefill cannot be used at the same time")
        sys.exit(1)

    if steps:
        _steps_test(target_config, worker_counts[0], namespace, primary_key, tables, num_inserts, extra_option, timeout, batch, clean, steps)
    else:
        _normal_test(target_config, worker_counts, namespace, runs, primary_key, tables, num_inserts, prefill, extra_option, timeout, batch, clean)


def _normal_test(target_config, worker_counts, namespace, runs, primary_key, tables, num_inserts, prefill, extra_option, timeout, batch, clean):
    run_config, target_module = _prepare_run_config(target_config, primary_key, tables, num_inserts, prefill, int(batch) if batch else None, clean, extra_option)

    print(f"Workers\tMin\tMax\tAvg")
    for worker_count in worker_counts:
        run_results = [one_run(worker_count, run_config, target_module, timeout, namespace)["sum"]["ops_per_second"] for _ in range(runs)]
        result_min = round(min(run_results))
        result_max = round(max(run_results))
        result_avg = round(int(sum(run_results)/len(run_results)))
        print(f"{worker_count:2}\t{result_min:6}\t{result_max:6}\t{result_avg:6}")


def _steps_test(target_config, workers, namespace, primary_key, tables, num_inserts, extra_option, timeout, batch, clean, steps):
    run_config, target_module = _prepare_run_config(target_config, primary_key, tables, num_inserts, 0, int(batch) if batch else None, clean, extra_option)
    run_config_continued, _ = _prepare_run_config(target_config, primary_key, tables, num_inserts, 0, int(batch) if batch else None, False, extra_option)
    stepsize = workers*num_inserts
    width = len(f"{stepsize*steps}")
    print(f"Stepsize: {stepsize}")
    print(f"Level".rjust(width)+"\tInserts/s")
    for step in range(steps):
        fill = f"{step*stepsize}".rjust(width)
        inserts = int(round(one_run(workers, run_config, target_module, timeout, namespace)["sum"]["ops_per_second"], -1))
        run_config = run_config_continued
        print(f"{fill}\t{inserts:6}")


def _prepare_run_config(target_config, primary_key, tables, num_inserts, prefill, batch, clean, extra_options):
    config = target_config
    config.update({
        "task": "insert",
        "num_inserts": num_inserts,
        "prefill": int(prefill),
        "primary_key": primary_key,
        "use_multiple_tables": tables=="multiple",
        "clean_database": clean,
    })
    if batch:
        config["batch_mode"] = True
        config["batch_size"] = batch
    for option in extra_options:
        k, v = option.split("=", 1)
        config[k] = v
    return base64.b64encode(json.dumps(config).encode("utf-8")).decode("utf-8"), config["module"]
    

def _read_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config
