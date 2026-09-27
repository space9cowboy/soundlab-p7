#!/usr/bin/env bash
set -euo pipefail
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml
kubectl -n ingress-nginx patch deployment ingress-nginx-controller --type=merge -p '{"spec":{"template":{"spec":{"nodeSelector":{"ingress-ready":"true","kubernetes.io/os":"linux"},"tolerations":[{"key":"node-role.kubernetes.io/control-plane","operator":"Exists","effect":"NoSchedule"}]}}}}'
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=180s
NOEUD=$(kubectl -n ingress-nginx get pods -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].spec.nodeName}')
[[ "$NOEUD" == *control-plane ]] || { echo "CONTROLEUR_MAL_PLACE $NOEUD"; exit 1; }
echo "INGRESS_OK $NOEUD"
