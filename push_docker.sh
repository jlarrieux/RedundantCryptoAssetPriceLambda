#!/bin/bash

source variables.sh

# Log in to AWS ECR
aws_ecr_login

# push to aws ecr
sudo docker push $ECR_URL/$IMAGE_NAME:latest