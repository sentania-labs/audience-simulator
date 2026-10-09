#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image="${1:?image required}"
cluster="audience-smoke-$$"
scratch="$(mktemp -d)"
export KUBECONFIG="$scratch/kubeconfig"
pf=""
cleanup() {
  if [[ -n "$pf" ]]; then kill "$pf" 2>/dev/null || true; fi
  kind delete cluster --name "$cluster"
  rm -rf "$scratch"
}
trap cleanup EXIT
kind create cluster --name "$cluster" --wait 120s
kind load docker-image "$image" --name "$cluster"
export MEETING_PASSWORD ADMIN_PASSWORD
MEETING_PASSWORD="$(openssl rand -hex 24)"
ADMIN_PASSWORD="$(openssl rand -hex 24)"
python3 - <<'PY' | kubectl create -f -
import os,json
print(json.dumps(dict(apiVersion='v1',kind='Secret',metadata={'name':'audience-test'},
 stringData={key:os.environ[key] for key in ('MEETING_PASSWORD','ADMIN_PASSWORD')})))
PY
helm install audience charts/audience-simulator --set existingSecret=audience-test   --set image.repository="${image%:*}" --set image.tag="${image##*:}"   --set config.PROVIDER_MODE=mock --set-string config.COOKIE_SECURE=false   --set-string config.ALLOWED_ORIGINS=http://localhost:8000 --wait --timeout 120s
kubectl port-forward service/audience 18081:8000 >"$scratch/forward.log" 2>&1 &
pf=$!
export SMOKE_URL=http://127.0.0.1:18081
for attempt in $(seq 1 30); do
  if curl -fsS "$SMOKE_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
.venv/bin/python scripts/smoke.py
# Recreate the pod to prove the PVC preserves the admin ledger.
kubectl rollout restart deployment/audience
kubectl rollout status deployment/audience --timeout=120s
kill "$pf" 2>/dev/null || true
kubectl port-forward service/audience 18081:8000 >"$scratch/forward.log" 2>&1 &
pf=$!
for attempt in $(seq 1 30); do
  if curl -fsS "$SMOKE_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 1
done
.venv/bin/python - <<'PY'
import os,httpx
with httpx.Client(base_url=os.environ['SMOKE_URL']) as c:
    assert c.post('/api/auth/admin/login',headers={'origin':'http://localhost:8000'},json={'password':os.environ['ADMIN_PASSWORD']}).status_code==200
    assert c.get('/api/admin').json()['meetings']
print('PVC restart persistence passed.')
PY
