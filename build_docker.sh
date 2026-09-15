#!/bin/bash

source variables.sh

if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
    echo "ERROR: Working tree has uncommitted changes. Commit or stash before building." >&2
    exit 1
fi

# Log in to AWS ECR
aws_ecr_login

# Deleting olg images
delete_old_images

# Clean up docker
clean_up_docker


# Get personal access token that is saved in git-credentials
PAT=$(awk -F '[:@]' '{print $3}' ~/.git-credentials)
export PAT

# Build the Docker image
NEW_VERSION=$(version-bump "$VERSION")
sed -i "s/^VERSION=.*/VERSION=$NEW_VERSION/" variables.sh
VERSION=$NEW_VERSION
git add variables.sh
git commit -m "v$VERSION"
git tag "v$VERSION"
echo "Tagged v$VERSION"

if ! git push origin main; then
    echo "WARNING: Failed to push main to origin; continuing with the build." >&2
fi
if ! git push origin --tags; then
    echo "WARNING: Failed to push tags to origin; continuing with the build." >&2
fi

sudo --preserve-env=PAT docker build --secret id=git_pat,env=PAT --build-arg APP_VERSION=$VERSION -t $IMAGE_NAME .

# Tag the Docker image for AWS ECR
sudo docker tag $IMAGE_NAME:latest $ECR_URL/$IMAGE_NAME:latest
