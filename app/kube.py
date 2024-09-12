import kubernetes_asyncio.client as kube_client
import kubernetes_asyncio.config as kube_config


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


