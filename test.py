import kubernetes.config as kube_config
from kubernetes import client as kube_client
from kubernetes.client import V1Toleration
from kubernetes.utils.quantity import parse_quantity

kube_config.load_kube_config()
api_instance = kube_client.CoreV1Api()

cpu_default = "2"
mem_default = "4Gi"
storage_default = "500Gi"


def _set_container_resources(container: dict) -> tuple[float, float, float]:
    if "resources" not in container:
        container["resources"] = {}

    requests: dict[str, str] = container["resources"].get("requests", {})
    limits: dict[str, str] = container["resources"].get("limits", {})

    cpu_request = requests.get("cpu", cpu_default)
    memory_request = requests.get("memory", mem_default)
    storage_request = requests.get("ephemeral-storage", storage_default)

    cpu_limit = limits.get("cpu", cpu_request)
    memory_limit = limits.get("memory", memory_request)
    storage_limit = limits.get(
        "ephemeral-storage", requests.get("ephemeral-storage", storage_request)
    )

    container["resources"] = {
        "requests": {
            "cpu": cpu_request,
            "memory": memory_request,
            "ephemeral-storage": storage_request,
        },
        "limits": {
            "cpu": cpu_limit,
            "memory": memory_limit,
            "ephemeral-storage": storage_limit,
        },
    }

    return (
        float(parse_quantity(cpu_limit)),
        float(parse_quantity(memory_limit) / 1024**3),
        float(parse_quantity(storage_limit) / 1024**3),
    )


def _set_pod_resources(pod_spec: dict) -> tuple[float, float, float]:
    if len(pod_spec.get("containers", [])) == 0:
        raise ValueError("No containers found in pod spec")

    # rahul: set default limits if they do not exist
    # because resource quotas require limits to be set
    cpu, memory, storage_gib = _set_container_resources(pod_spec["containers"][0])

    toleration: V1Toleration | None = None
    if cpu <= 31 and memory <= 127 and storage_gib <= 1949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="cpu-32-spot")
    elif cpu <= 95 and memory <= 179 and storage_gib <= 4949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="cpu-96-spot")
    elif cpu <= 62 and memory <= 490 and storage_gib <= 4949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="mem-512-spot")
    else:
        if memory > 490:
            raise ValueError(
                f"custom task requires too much RAM: {memory} GiB (max 490 GiB)"
            )
        elif storage_gib > 4949:
            raise ValueError(
                f"custom task requires too much storage: {storage_gib} GiB (max 4949"
                " GiB)"
            )
        elif cpu > 95:
            raise ValueError(f"custom task requires too many CPU cores: {cpu} (max 95)")
        elif memory > 179 and cpu > 62:
            raise ValueError(
                f"could not resolve cpu for high memory machine: requested {cpu} cores"
                " (max 62)"
            )
        elif cpu > 62 and memory > 179:
            raise ValueError(
                f"could not resolve memory for high cpu machine: requested {memory} GiB"
                " (max 179 GiB)"
            )
        else:
            raise ValueError(
                f"custom task resource limit is too high: {cpu} (max 95) cpu cores,"
                f" {memory} GiB (max 179 GiB) memory, or {storage_gib} GiB storage (max"
                " 4949 GiB)"
            )
    pod_spec["tolerations"] = [toleration.to_dict()]

    return cpu, memory, storage_gib


pod = {
    "metadata": {
        "name": "test-pod-3",
    },
    "spec": {
        "containers": [
            {
                "name": "test-container",
                "image": "busybox",
                "command": ["sleep", "3600"],
                "resources": {
                    "requests": {
                        "cpu": "100m",
                        "memory": "100Mi",
                    },
                    "limits": {
                        "cpu": "200m",
                        "memory": "200Mi",
                    },
                },
            },
        ],
    },
}

x = api_instance.read_namespaced_resource_quota(
    namespace="35437-development", name="project-quota"
)
print(x.spec.hard)
import sys

sys.exit(0)

pod_spec = pod["spec"]
metadata = pod["metadata"]

pod_name = metadata["name"]

pod_spec["service_account_name"] = "default"
pod_spec["runtimeClassName"] = "sysbox-runc"
pod_spec["node_selector"] = {"sysbox-runtime": "running"}

if "annotations" not in metadata:
    metadata["annotations"] = {}
metadata["annotations"][
    "io.kubernetes.cri-o.userns-mode"
] = "private:uidmapping=0:1048576:65536;gidmapping=0:1048576:65536"
metadata["annotations"]["cluster-autoscaler.kubernetes.io/safe-to-evict"] = "false"

if "labels" not in metadata:
    metadata["labels"] = {}
metadata["labels"]["latch/runtime"] = "nextflow"

cpu, mem, storage = _set_pod_resources(pod_spec)

for container in pod_spec.get("containers", []):
    if "securityContext" not in container:
        container["securityContext"] = {}
    container["securityContext"]["allowPrivilegeEscalation"] = False
    container["securityContext"]["privileged"] = False
    if "env" not in container:
        container["env"] = []
    container["env"].append(
        {
            "name": "TAR_OPTIONS",
            "value": "--no-same-owner",
        }
    )

api_instance.create_namespaced_pod(namespace="35437-development", body=pod)
