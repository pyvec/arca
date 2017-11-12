#!/bin/bash

docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_PASSWORD"
python setup.py deploy_docker_bases
