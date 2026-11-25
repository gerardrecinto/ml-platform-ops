# Runbook

## Errors or latency on /score
1. `kubectl -n mlplat get pods` and `kubectl -n mlplat logs deploy/mlplat --tail 100`.
2. If it started with a rollout: `kubectl -n mlplat rollout undo deploy/mlplat`, then investigate.
3. If it started with a model change: `python -m mlplat rollback`, update the ConfigMap, `kubectl -n mlplat rollout restart deploy/mlplat`.
4. Check node pressure and the HPA: `kubectl -n mlplat get hpa` and `kubectl top pods -n mlplat`.

## A model will not load
`mlplat_reload_failed` is 1: the registry file changed to something unusable and pods are still serving the previous model. Fix the file (valid JSON, `active` names a model that exists) and restart the pods. A pod that starts with a bad file stays out of the Service until it is fixed.

## Promote a model
`python -m mlplat promote <version>` refuses a model that scores more than 0.02 below the active one on `tests/holdout.json`. Update the ConfigMap with the new registry file and roll the deployment. Keep the previous version in the registry for rollback.
