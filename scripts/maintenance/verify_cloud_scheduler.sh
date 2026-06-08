#!/bin/bash
# verify_cloud_scheduler.sh

echo "Verificando job do Cloud Scheduler: auditoria-automacao-run"

# Requer gcloud autenticado e com permissoes
gcloud scheduler jobs describe auditoria-automacao-run \
  --location=southamerica-east1 \
  --format='value(schedule,attemptDeadline,httpTarget.uri)'

echo ""
echo "O resultado esperado eh:"
echo "*/10 * * * *"
echo "1800s"
echo "https://.../api/automation/cron/run"
