# ofs-repro

To reproduce the issue:
- Change the image registry to your own in Justfile. Build the image with `just dbnp`.
- Deploy OFS secret into the cluster.
- Deploy the CSI volume and roles into the cluster with `kubectl apply -f ./k8s/pv.yaml`.
- Test the deployment with `kubectl apply -f ./k8s/pod.yaml`.

