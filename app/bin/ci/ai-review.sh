#!/usr/bin/env bash
set -axe
MR_ID=${1}
PROJECT_ID=${2}
GITLAB_URL=${3}
GITLAB_TOKEN=${4}
JOB_ID=${5}
LLM_TYPE=${6}
LLM_KEY=${7}
LLM_URL=${8}
LLM_MODEL=${9}
LLM_MAX_TOKENS=${10}
LLM_TEMPERATURE=${11}
LLM_PROMPT=${12}
CONTAINER="ai-review-$JOB_ID"
EXEC="docker exec -w /test $CONTAINER"
docker rm -f $CONTAINER || true
docker run -d --rm --name $CONTAINER suap-dev
git pull origin master
docker cp $(pwd)/bin/reviewer $CONTAINER:/test
$EXEC python main.py --mr-id $MR_ID --project-id $PROJECT_ID --gitlab-url $GITLAB_URL --gitlab-token $GITLAB_TOKEN --llm-type $LLM_TYPE --llm-key $LLM_KEY --llm-url $LLM_URL --llm-model $LLM_MODEL --llm-max-tokens $LLM_MAX_TOKENS --llm-temperature $LLM_TEMPERATURE --llm-prompt "$LLM_PROMPT"
docker rm -f "$CONTAINER" || true
