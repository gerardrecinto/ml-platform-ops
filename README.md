# ml-platform-ops

[![CI](https://github.com/gerardrecinto/ml-platform-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/gerardrecinto/ml-platform-ops/actions/workflows/ci.yml)

How I would run an ML scoring platform on EKS: a Python scoring service, a model promotion gate that refuses a worse model, SLO burn-rate alerts with unit tests, Kubernetes manifests that survive a pod delete and a bad rollout, and Terraform for EKS and model storage.

The Terraform is validated in CI. See "What is verified".

## Run it

```bash
git clone https://github.com/gerardrecinto/ml-platform-ops && cd ml-platform-ops
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pytest -q
./scripts/kind-test.sh     # needs Docker, kind, kubectl; about 2 minutes
```

## What is in it

| Piece | What it does |
|---|---|
| `src/mlplat/service.py` | Scoring API on the standard library: `POST /score`, `/healthz`, `/readyz`, `/metrics` (request counts by code, latency histogram, model version, reload failure flag). Handles SIGTERM and SIGHUP. |
| `src/mlplat/gate.py` | `python -m mlplat promote <version>` activates a model only if it loads and scores no more than 0.02 below the active model on a holdout set; `rollback` swaps back. |
| `monitoring/slo.yml` | 99.9% availability SLO with fast burn (page) and slow burn (ticket) alerts, a p99 latency alert and a model reload alert. `slo.test.yml` has promtool unit tests. |
| `deploy/k8s/mlplat.yaml` | Two replicas, zero unavailable during a rollout, readiness and liveness probes, non-root read-only container, pod disruption budget, HPA. |
| `scripts/kind-test.sh` | On a kind cluster: score through the Service, delete a pod under 200 requests, break a rollout with a missing image, undo it. |
| `terraform/` | EKS (module `terraform-aws-modules/eks`), a versioned encrypted private S3 bucket for model artifacts, a service account role that can only read that bucket, and a node CPU alarm. |

## Promotion gate

```bash
python -m mlplat promote v2 --registry registry/registry.json   # already active: refused
python -m mlplat rollback --registry registry/registry.json     # active: v1
```

## Design choices

- **Gate on a holdout set, not on loading.** A model that loads can still score worse. Cost: the holdout is 10 rows here and a real one needs thousands, refreshed as fraud patterns change. Flip to a shadow period on live traffic once a baseline exists.
- **A bad registry keeps the old model serving.** Readiness stays up and `mlplat_reload_failed` goes to 1 so a ticket fires. Failing readiness would pull every pod out of the Service at once. Cost: a stale model can run quietly if nobody reads the alert.
- **Alert on burn rate, not on error count.** A short spike that costs 1% of the monthly budget should not page; a steady 2% error rate should. Cost: the rules are harder to read than a plain threshold.
- **Terraform uses an existing VPC.** Networking is owned elsewhere in most shops. Cost: the config cannot stand up alone.

## What is verified

- **Run here:** 11 pytest tests; promtool rule tests for fast burn, no burn and reload failure; a kind cluster where the Service answered, 0 of 200 requests failed while one pod was deleted (one run), a rollout to a missing image hit its progress deadline and `rollout undo` restored service; `terraform validate` and `fmt` pass.
- **Not done:** Terraform was never applied, so no EKS cluster, IAM role or bucket exists from this code. The HPA is applied but kind has no metrics server, so it never scaled. The model is a small logistic score on made-up features, not a trained model. Latency alerts are unit tested on synthetic series, not on real traffic. No Snowflake, no real fraud data.

MIT licensed.
