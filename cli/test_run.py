import subprocess
import urllib.request as urllib_request
import json
from .kubernetes_helper import Kubernetes


def http_request(url):
    response = urllib_request.urlopen(url)
    body = response.read().decode('utf-8')
    response.close()
    return body


def one_run(num_workers, run_config, target_module, timeout, namespace):
    kube = Kubernetes()
    res = subprocess.run(["helm", "install", "-n", namespace, "dbtest", ".", "--set", f"workers={num_workers}", "--set", f"run_config={run_config}", 
                            "--set", f"target_module={target_module}", "--set", f"namespace={namespace}"], cwd="deployment", stdout=subprocess.DEVNULL)
    res.check_returncode()
    res = subprocess.run(f"kubectl wait --for=condition=complete --timeout={timeout}s -n {namespace} job dbtest-worker".split(" "), stdout=subprocess.DEVNULL)
    res.check_returncode()
    collector_pod_name = kube.find_pod(namespace, "app", "dbtest-collector")
    kube.patch_socket()
    results = json.loads(http_request(f"http://{collector_pod_name}.pod.{namespace}.kubernetes:5000/report"))
    res = subprocess.run(f"helm uninstall -n {namespace} dbtest".split(" "), stdout=subprocess.DEVNULL)
    res.check_returncode()
    return results["sum"]["ops_per_second"]
