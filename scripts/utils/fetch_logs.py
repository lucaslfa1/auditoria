import subprocess
import json

cmd = [
    "gcloud.cmd", "logging", "read",
    'resource.type="cloud_run_revision" AND resource.labels.service_name="auditoria" AND textPayload:"OBS miss"',
    "--limit", "5",
    "--project", "auditoria-nstech",
    "--format", "json"
]

res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
