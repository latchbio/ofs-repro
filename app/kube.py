from dataclasses import dataclass

import kubernetes_asyncio.client as kube_client
import kubernetes_asyncio.config as kube_config
from kubernetes.utils.quantity import parse_quantity
from kubernetes_asyncio.client import V1Pod, V1Toleration

finalizer = "latch.bio/nextflow"


class AsyncK8sClient:
    api_client: kube_client.ApiClient = None
    core_v1_api: kube_client.CoreV1Api = None
    storage_v1_api: kube_client.StorageV1Api = None

    async def initialize(self):
        kube_config.load_incluster_config()

        self.api_client = kube_client.ApiClient()
        await self.api_client.__aenter__()

        self.core_v1_api = kube_client.CoreV1Api(self.api_client)
        self.storage_v1_api = kube_client.StorageV1Api(self.api_client)

    async def close(self):
        await self.api_client.__aexit__(None, None, None)


client = AsyncK8sClient()


cpu_default = "2"
mem_default = "4Gi"
storage_default = "100Gi"


@dataclass(frozen=True)
class ContainerResources:
    cpu_millicores: int
    memory_bytes: int
    storage_bytes: int


def _set_container_resources(container: dict) -> ContainerResources:
    if "resources" not in container:
        container["resources"] = {}

    requests: dict[str, str] = container["resources"].get("requests", {})
    limits: dict[str, str] = container["resources"].get("limits", {})

    # rahul: set default limits if they do not exist
    # because resource quotas require limits to be set
    cpu_request = requests.get("cpu", cpu_default)
    memory_request = requests.get("memory", mem_default)
    storage_request = requests.get("ephemeral-storage", storage_default)

    cpu_limit = limits.get("cpu", cpu_request)
    memory_limit = limits.get("memory", memory_request)
    storage_limit = limits.get("ephemeral-storage", storage_request)

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

    return ContainerResources(
        int(parse_quantity(cpu_limit) * 1000),
        int(parse_quantity(memory_limit)),
        int(parse_quantity(storage_limit)),
    )


def set_pod_resources(pod: V1Pod) -> ContainerResources:
    pod_spec = pod["spec"]

    if len(pod_spec.get("containers", [])) == 0:
        raise ValueError("No containers found in pod spec")

    resources = _set_container_resources(pod_spec["containers"][0])
    cpu, memory_gib, storage_gib = (
        resources.cpu_millicores / 1000,
        resources.memory_bytes / 1024**3,
        resources.storage_bytes / 1024**3,
    )

    toleration: V1Toleration | None = None
    if cpu <= 31 and memory_gib <= 127 and storage_gib <= 1949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="cpu-32-spot")
    elif cpu <= 95 and memory_gib <= 179 and storage_gib <= 4949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="cpu-96-spot")
    elif cpu <= 62 and memory_gib <= 490 and storage_gib <= 4949:
        toleration = V1Toleration(effect="NoSchedule", key="ng", value="mem-512-spot")
    else:
        if memory_gib > 490:
            raise ValueError(
                f"custom task requires too much RAM: {memory_gib} GiB (max 490 GiB)"
            )
        elif storage_gib > 4949:
            raise ValueError(
                f"custom task requires too much storage: {storage_gib} GiB (max 4949"
                " GiB)"
            )
        elif cpu > 95:
            raise ValueError(f"custom task requires too many CPU cores: {cpu} (max 95)")
        elif memory_gib > 179 and cpu > 62:
            raise ValueError(
                f"could not resolve cpu for high memory machine: requested {cpu} cores"
                " (max 62)"
            )
        elif cpu > 62 and memory_gib > 179:
            raise ValueError(
                f"could not resolve memory for high cpu machine: requested {memory_gib} GiB"
                " (max 179 GiB)"
            )
        else:
            raise ValueError(
                f"custom task resource limit is too high: {cpu} (max 95) cpu cores,"
                f" {memory_gib} GiB (max 179 GiB) memory, or {storage_gib} GiB storage (max"
                " 4949 GiB)"
            )
    pod_spec["tolerations"] = [toleration.to_dict()]

    return resources


def update_pod_spec(
    pod: V1Pod,
    execution_token: str,
    task_execution_id: int,
    namespace: str,
    *,
    add_finalizer: bool = False,
):
    pod_spec = pod["spec"]
    metadata = pod["metadata"]

    if pod_spec is None or metadata is None:
        raise ValueError("Pod spec or metadata not found")

    metadata["namespace"] = namespace

    pod_name = metadata["name"]
    if pod_name is None:
        raise ValueError("Pod name not found")

    pod_spec["serviceAccountName"] = "default"
    pod_spec["runtimeClassName"] = "sysbox-runc"
    pod_spec["nodeSelector"] = {"sysbox-runtime": "running"}

    if "annotations" not in metadata:
        metadata["annotations"] = {}
    metadata["annotations"][
        "io.kubernetes.cri-o.userns-mode"
    ] = "private:uidmapping=0:1048576:65536;gidmapping=0:1048576:65536"
    metadata["annotations"]["cluster-autoscaler.kubernetes.io/safe-to-evict"] = "false"

    if "labels" not in metadata:
        metadata["labels"] = {}
    metadata["labels"]["latch/runtime"] = "nextflow"
    metadata["labels"]["execution-id"] = str(execution_token)
    metadata["labels"]["latch-nf/task-execution-id"] = str(task_execution_id)

    for container in pod_spec.get("containers", []):
        if "securityContext" not in container:
            container["securityContext"] = {}
        container["securityContext"]["allowPrivilegeEscalation"] = False
        container["securityContext"]["privileged"] = False

        container.setdefault("env", []).append(
            {
                "name": "TAR_OPTIONS",
                "value": "--no-same-owner",
            }
        )

    if add_finalizer:
        if "finalizers" not in metadata:
            metadata["finalizers"] = []

        if finalizer not in metadata["finalizers"]:
            metadata["finalizers"].append(finalizer)
