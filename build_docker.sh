#!/bin/bash

source variables.sh

# Log in to AWS ECR
aws_ecr_login

# Deleting olg images
delete_old_images

# Clean up docker
clean_up_docker


# Get personal access token that is saved in git-credentials
PAT=$(awk -F '[:@]' '{print $3}' ~/.git-credentials)

# Build the Docker image
sudo docker build --build-arg GIT_PAT=$PAT -t $IMAGE_NAME .

# Tag the Docker image for AWS ECR
sudo docker tag $IMAGE_NAME:latest $ECR_URL/$IMAGE_NAME:latest