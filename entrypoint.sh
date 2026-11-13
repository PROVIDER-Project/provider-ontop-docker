#!/bin/bash
set -euo pipefail

# Preserve upstream arbitrary-command and CLI-help behaviour.
args=("$@")
case "${1:-}" in
    ""|-*) command=endpoint ;;
    ontop) command=${2:-help} ;;
    *) exec /opt/ontop/entrypoint-original.sh "$@" ;;
esac
case "$command" in
    endpoint|query|materialize|validate|bootstrap|extract-db-metadata) ;;
    *) exec /opt/ontop/entrypoint-original.sh "$@" ;;
esac
for arg in "$@"; do
    case "$arg" in -h|--help) exec /opt/ontop/entrypoint-original.sh "$@" ;; esac
done

# An explicit CLI properties file takes precedence over ONTOP_PROPERTIES_FILE.
source_properties=${ONTOP_PROPERTIES_FILE:-}
property_index=-1
inline=false
for ((i=0; i<${#args[@]}; i++)); do
    case "${args[i]}" in
        -p|--properties)
            if ((i+1 >= ${#args[@]})); then
                echo 'Missing argument for --properties/-p' >&2
                exit 1
            fi
            ((i+=1))
            source_properties=${args[i]}
            property_index=$i
            inline=false
            ;;
        --properties=*)
            source_properties=${args[i]#*=}
            property_index=$i
            inline=true
            ;;
    esac
done
runtime_properties=$(java -cp /opt/ontop/runtime/classes PropertyOverrides "$source_properties")
export ONTOP_PROPERTIES_FILE=$runtime_properties
if ((property_index >= 0)); then
    if "$inline"; then
        args[property_index]="--properties=$runtime_properties"
    else
        args[property_index]=$runtime_properties
    fi
fi
exec /opt/ontop/entrypoint-original.sh "${args[@]}"
