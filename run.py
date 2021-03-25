import base64
import json
import click
import yaml
from cli.test_run import one_run


@click.command()
@click.option('-t', '--target', required=True, help="Name of the target")
@click.option('-c', '--config', default="config.yaml", help="Name of the config file to use")
@click.option('-w', '--workers', default="1,4,8,12,16", help="Sets of worker counts to use, separate by comma without space, default='1,4,8,12,16'")
@click.option('-r', '--runs', default=3, help='Number of runs per worker count, default=3')
@click.option("--primary-key", default="db", type=click.Choice(['db', 'client'], case_sensitive=False))
@click.option("--tables", default="single", type=click.Choice(['single', 'multiple'], case_sensitive=False))
@click.option("--num-inserts", default=10000, help="Number of inserts per worker, default=10000")
@click.option("--extra-option", multiple=True, help="Extra options for the database module")
@click.option("--timeout", default=600, help="Timeout in seconds to wait for one run to complete. Increase this if you use higher number of inserts. default=600")
def main(target, config, workers, runs, primary_key, tables, num_inserts, extra_option, timeout):
    worker_counts = map(lambda el: int(el), workers.split(","))
    config = _read_config(config)
    target_config = config["targets"][target]
    namespace = config.get("namespace", "default")
    run_config, target_module = _prepare_run_config(target_config, primary_key, tables, num_inserts, extra_option)

    print(f"Worker\tMin\tMax\tAvg")
    for worker_count in worker_counts:
        run_results = [one_run(worker_count, run_config, target_module, timeout, namespace) for _ in range(runs)]
        result_min = round(min(run_results))
        result_max = round(max(run_results))
        result_avg = round(int(sum(run_results)/len(run_results)))
        print(f"{worker_count:2}\t{result_min:5}\t{result_max:5}\t{result_avg:5}")



def _prepare_run_config(target_config, primary_key, tables, num_inserts, extra_options):
    config = target_config
    config.update({
        "num_inserts": num_inserts,
        "primary_key": primary_key,
        "use_multiple_tables": tables=="multiple"
    })
    for option in extra_options:
        k, v = option.split("=", 1)
        config[k] = v
    return base64.b64encode(json.dumps(config).encode("utf-8")).decode("utf-8"), config["module"]
    

def _read_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config


if __name__ == '__main__':
    main()
