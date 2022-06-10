#!/bin/bash

ssh_url=$(../vast-python/vast.py ssh-url)
ssh "$ssh_url" -o StrictHostKeyChecking=no -L 8888:localhost:8888 -t 'cd third-eye-api; bash --login'
