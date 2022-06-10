#!/bin/bash

git add -A && git commit -m "changes" && git push
ssh_url=$(../vast-python/vast.py ssh-url)
ssh "$ssh_url" -o StrictHostKeyChecking=no "cd third-eye-api && git pull"
