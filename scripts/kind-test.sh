#!/usr/bin/env bash
# On a throwaway kind cluster: deploy, score through the Service, delete a pod under load, then break a rollout and undo it.
set -euo pipefail
cd "$(dirname "$0")/.."
kind get clusters 2>/dev/null | grep -qx mlplat || kind create cluster --name mlplat --wait 90s
docker build -q -t mlplat:0.1.0 .
kind load docker-image mlplat:0.1.0 --name mlplat
kubectl apply -f deploy/k8s/mlplat.yaml
kubectl -n mlplat rollout status deploy/mlplat --timeout=90s

probe() { kubectl -n mlplat run "probe-$1" --rm -i --restart=Never --image=curlimages/curl:8.11.0 --command -- sh -c "$2" 2>/dev/null; }

echo "== score through the Service"
probe a 'curl -s -XPOST mlplat/score -d "{\"features\":{\"amount_k\":2,\"country_mismatch\":1,\"new_device\":1,\"velocity_1h\":4}}"'; echo

echo "== delete a pod while 200 requests run"
(sleep 1; kubectl -n mlplat get pod -l app=mlplat -o name | head -1 | xargs kubectl -n mlplat delete --wait=false >/dev/null) &
fails=$(probe b 'f=0; i=0; while [ $i -lt 200 ]; do curl -s -f -m 2 -XPOST mlplat/score -d "{\"features\":{}}" >/dev/null || f=$((f+1)); i=$((i+1)); sleep 0.05; done; echo FAILED=$f' | grep -o 'FAILED=[0-9]*' | cut -d= -f2)
wait
echo "failed requests: $fails of 200"
kubectl -n mlplat rollout status deploy/mlplat --timeout=90s

echo "== bad rollout, then undo"
kubectl -n mlplat set image deploy/mlplat mlplat=mlplat:does-not-exist
if kubectl -n mlplat rollout status deploy/mlplat --timeout=60s; then echo "unexpected: bad image rolled out"; exit 1; fi
kubectl -n mlplat rollout undo deploy/mlplat
kubectl -n mlplat rollout status deploy/mlplat --timeout=90s
probe c 'curl -s -XPOST mlplat/score -d "{\"features\":{}}"'; echo
echo "OK failed_during_pod_delete=$fails"
