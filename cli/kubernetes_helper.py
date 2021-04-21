import time
import socket
from kubernetes import client, config
from kubernetes.stream import portforward


class Kubernetes:

    def __init__(self):
        config.load_kube_config()
        self.api_instance = client.CoreV1Api()

    def find_pod(self, namespace, label_key, label_value):
        for pod in self.api_instance.list_namespaced_pod(namespace).items:
            labels = pod.metadata.labels
            if labels and labels.get(label_key) == label_value:
                return pod.metadata.name

    def get_pods(self, namespace, label_key, label_value):
        for pod in self.api_instance.list_namespaced_pod(namespace).items:
            labels = pod.metadata.labels
            if labels and labels.get(label_key) == label_value:
                yield pod

    def check_if_pods_finished(self, namespace, label_key, label_value):
        pods = self.get_pods(namespace, label_key, label_value)
        all_finished = True
        for pod in pods:
            if pod.status.phase == "Failed":
                raise Exception("At least one pod of the job failed")
            if pod.status.phase != "Succeeded":
                all_finished = False
        return all_finished

    def wait_for_pods_terminated(self, namespace, label_key, label_value):
        for _ in range(10):
            pods = list(self.get_pods(namespace, label_key, label_value))
            if len(pods) == 0:
                return
            time.sleep(5)
        raise Exception("Failed to wait for pods to terminate")

    def patch_socket(self):
        """Taken from https://github.com/kubernetes-client/python/blob/master/examples/pod_portforward.py and adapted
        """
        socket_create_connection = socket.create_connection

        def kubernetes_create_connection(address, *args, **kwargs):
            dns_name = address[0]
            if isinstance(dns_name, bytes):
                dns_name = dns_name.decode()
            dns_name = dns_name.split(".")
            if dns_name[-1] != 'kubernetes':
                return socket_create_connection(address, *args, **kwargs)
            if len(dns_name) not in (3, 4):
                raise RuntimeError("Unexpected kubernetes DNS name.")
            namespace = dns_name[-2]
            name = dns_name[0]
            port = address[1]
            if len(dns_name) == 4:
                if dns_name[1] in ('svc', 'service'):
                    service = self.api_instance.read_namespaced_service(name, namespace)
                    for service_port in service.spec.ports:
                        if service_port.port == port:
                            port = service_port.target_port
                            break
                    else:
                        raise RuntimeError(
                            "Unable to find service port: %s" % port)
                    label_selector = []
                    for key, value in service.spec.selector.items():
                        label_selector.append("%s=%s" % (key, value))
                    pods = self.api_instance.list_namespaced_pod(
                        namespace, label_selector=",".join(label_selector)
                    )
                    if not pods.items:
                        raise RuntimeError("Unable to find service pods.")
                    name = pods.items[0].metadata.name
                    if isinstance(port, str):
                        for container in pods.items[0].spec.containers:
                            for container_port in container.ports:
                                if container_port.name == port:
                                    port = container_port.container_port
                                    break
                            else:
                                continue
                            break
                        else:
                            raise RuntimeError("Unable to find service port name: %s" % port)
                elif dns_name[1] != 'pod':
                    raise RuntimeError("Unsupported resource type: %s" % dns_name[1])
            try:
                pf = portforward(self.api_instance.connect_get_namespaced_pod_portforward,
                            name, namespace, ports=str(port))
            except: # Retry in case of error
                pf = portforward(self.api_instance.connect_get_namespaced_pod_portforward,
                            name, namespace, ports=str(port))
            return pf.socket(port)
        socket.create_connection = kubernetes_create_connection
