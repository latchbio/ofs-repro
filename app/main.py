import asyncio
import random
import shutil
from pathlib import Path

from kubernetes_asyncio.client import (
    V1Container,
    V1EnvVar,
    V1ObjectMeta,
    V1PersistentVolumeClaimVolumeSource,
    V1Pod,
    V1PodSpec,
    V1Volume,
    V1VolumeMount,
)

from .kube import client as kube_client

pvc_name = "ofs-repro-development-objectivefs-pvc"

async def create_and_monitor_pod(folder: str, shared_dir: Path) -> None:
    pod_name = f"script-runner-{folder}"

    await asyncio.sleep(random.uniform(1, 5))

    pod = V1Pod(
        metadata=V1ObjectMeta(
            name=pod_name,
            namespace="ofs-repro",
            labels={"app": "script-runner"}
        ),
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="script-runner",
                    image="812206152185.dkr.ecr.us-west-2.amazonaws.com/latch-base:fe0b-main",
                    command=["python", f"/nf-workdir/{folder}/script.py"],
                    volume_mounts=[
                        V1VolumeMount(
                            name="shared-volume",
                            mount_path="/nf-workdir"
                        )
                    ],
                    env=[
                        V1EnvVar(
                            name="LATCH_RUN_ID",
                            value=folder
                        )
                    ]
                )
            ],
            volumes=[
                V1Volume(
                    name="shared-volume",
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                )
            ],
            restart_policy="Never"
        )
    )

    try:
        await kube_client.core_v1_api.create_namespaced_pod(namespace="ofs-repro", body=pod)
        print(f"Created pod: {pod_name}")

        while True:
            pod_status = await kube_client.core_v1_api.read_namespaced_pod_status(name=pod_name, namespace="ofs-repro")
            if pod_status.status.phase in ["Succeeded", "Failed"]:
                break
            await asyncio.sleep(5)

        exitstatus_file = shared_dir / folder / "exitcode.txt"
        if exitstatus_file.exists():
            with open(exitstatus_file, "r") as f:
                exitstatus = f.read().strip()
            print(f"Pod {pod_name} exitstatus: {exitstatus}")
        else:
            raise Exception(f"Pod {pod_name} exitstatus file not found at {exitstatus_file}")

        await kube_client.core_v1_api.delete_namespaced_pod(name=pod_name, namespace="ofs-repro")

    except Exception as e:
        print(f"Error with pod {pod_name}: {str(e)}")

async def main() -> None:
    shared_dir = Path("/nf-workdir")

    for item in shared_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    subfolders = [f"task{i}" for i in range(100)]

    for folder in subfolders:
        subfolder_path = shared_dir / folder
        subfolder_path.mkdir(parents=True, exist_ok=True)
        print(f"Created subfolder: {subfolder_path}")

    random_data_file = shared_dir / "random_data.txt"
    with open("/root/app/random_1mb.data", "rb") as source_file:
        random_content = source_file.read()
    random_data_file.write_bytes(random_content)

    for folder in subfolders:
        task_folder = shared_dir / folder
        script_path = Path("./app/script.py")
        task_script_path = task_folder / "script.py"
        task_script_path.write_text(script_path.read_text())

        data_symlink = task_folder / "random_data.txt"
        data_symlink.symlink_to(random_data_file)

    await kube_client.initialize()

    tasks = [create_and_monitor_pod(folder, shared_dir) for folder in subfolders]
    await asyncio.gather(*tasks)

    await kube_client.close()
    print("Kubernetes client closed")

if __name__ == "__main__":
    asyncio.run(main())
    print("Main function completed")
