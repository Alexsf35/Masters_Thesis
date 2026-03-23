#!/bin/bash

# 1. Encontrar a pasta mais recente no biocypher-out
LATEST_DIR=$(find biocypher-out -mindepth 1 -maxdepth 1 -type d ! -name "latest" | sort -r | head -n 1)

if [ -z "$LATEST_DIR" ]; then
    echo "❌ Nenhuma pasta encontrada em biocypher-out!"
    exit 1
fi

echo "📂 Pasta detetada: $LATEST_DIR"

# 2. Extrair apenas o nome da pasta (ex: 20260320221720)
FOLDER_NAME=$(basename "$LATEST_DIR")

# 3. Atualizar o .env para o Docker usar no IMPORT_DIR
echo "IMPORT_DIR=biocypher-out/$FOLDER_NAME" > .env
echo "⚙️ .env atualizado com sucesso."

# 4. Garantir que o script nativo do BioCypher tem permissões de execução
SCRIPT_PATH="$LATEST_DIR/neo4j-admin-import-call.sh"

if [ -f "$SCRIPT_PATH" ]; then
    # Corrigir quebras de linha do Windows e dar permissões
    sed -i 's/\r$//' "$SCRIPT_PATH"
    chmod +x "$SCRIPT_PATH"
    echo "✨ Permissões dadas ao script nativo: $SCRIPT_PATH"
else
    echo "⚠️ Aviso: O ficheiro $SCRIPT_PATH não foi encontrado!"
fi