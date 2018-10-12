#!/bin/sh

[ -z "$1" ] && echo "Need to specify version" && exit 1

docker build -t "concourse-http-api-resource:$1" .
docker tag "concourse-http-api-resource:$1" "overminddl1/concourse-http-api-resource:$1"
docker push overminddl1/concourse-http-api-resource:$1

