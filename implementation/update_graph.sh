#!/bin/bash
set -e # Stop on any error

echo "--- 1. Force cleaning Podman state ---"
# We use native podman to bypass compose lock issues
podman ps -q --filter "name=implementation" | xargs -r podman rm -f
podman volume rm implementation_biocypher_neo4j_volume || true

echo "--- 3. Preparing latest output ---"
bash prepare_latest.sh

echo "--- 4. Fixing host permissions ---"
# Get current folder name from prepare_latest logic
IMPORT_DIR=$(ls -dt biocypher-out/*/ | head -1)
podman unshare chown -R 0:0 "$IMPORT_DIR" .env scripts/

echo "--- 5. Starting Import (Sequential) ---"
podman-compose up import

echo "--- 6. Fixing internal volume permissions ---"
podman run --rm --user root -v implementation_biocypher_neo4j_volume:/data \
    docker.io/library/alpine sh -c "chown -R $(id -u):$(id -g) /data && rm -f /data/databases/store_lock /data/databases/neo4j/store_lock"

echo "--- 7. Starting Neo4j Server ---"
podman-compose up -d deploy

echo "--- DONE. Check http://localhost:7474 ---"