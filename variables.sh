#!/bin/bash

# Define variable for ECR repository URL
ECR_URL="601130035836.dkr.ecr.us-east-1.amazonaws.com"
IMAGE_NAME="price-service"

# Define a function for AWS ECR login
aws_ecr_login() {
    aws ecr get-login-password --region us-east-1 | sudo docker login --username AWS --password-stdin "$ECR_URL"
}

delete_old_images(){
  echo -e "\n About to delete all previous docker images\n"

  # Delete all Docker images if any exist
  if [ "$(sudo docker images -q)" ]; then
    sudo docker rmi --force $(sudo docker images -q)
  else
    echo "No Docker images to remove."
  fi
}


clean_up_docker() {
  echo "Cleaning up unused Docker resources..."
  # Prune all unused Docker objects without confirmation
  sudo docker system prune -f

  echo "Done pruning all unused containers"
}