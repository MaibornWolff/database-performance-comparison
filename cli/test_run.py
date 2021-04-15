import subprocess
import time
import urllib.request as urllib_request
import json
from .kubernetes_helper import Kubernetes


def http_request(url):
    for _ in range(10):
        try:
            response = urllib_request.urlopen(url)
            body = response.read().decode('utf-8')
            response.close()
            return body
        except:
            pass
    raise Exception("http_request failed with retry")


def one_run(num_workers, run_config, target_module, timeout, namespace):
    kube = Kubernetes()
    res = subprocess.run(["helm", "install", "-n", namespace, "dbtest", ".", "--set", f"workers={num_workers}", "--set", f"run_config={run_config}", 
                            "--set", f"target_module={target_module}", "--set", f"namespace={namespace}"], cwd="deployment", stdout=subprocess.DEVNULL)
    res.check_returncode()
    wait_time = 0
    while True:
        if kube.check_if_pods_finished(namespace, "app", "dbtest-worker"):
            break
        if kube.check_if_pods_finished(namespace, "app", "dbtest-collector"):
            raise Exception("Collector pod finished. Should not happen")
        if timeout > 0 and wait_time > timeout:
            raise Exception("Timeout reached")
        wait_time += 10
        time.sleep(10)
    collector_pod_name = kube.find_pod(namespace, "app", "dbtest-collector")
    kube.patch_socket()
    results = json.loads(http_request(f"http://{collector_pod_name}.pod.{namespace}.kubernetes:5000/report"))
    res = subprocess.run(f"helm uninstall -n {namespace} dbtest".split(" "), stdout=subprocess.DEVNULL)
    res.check_returncode()
    return results["sum"]["ops_per_second"]
