#!/bin/bash

ssh_url=$(../vast-python/vast.py ssh-url)
ssh "$ssh_url" -o StrictHostKeyChecking=no "sudo apt-get install curl -y && curl -o- https://raw.githubusercontent.com/andyshand/third-eye-api/main/install.sh > install.sh && source install.sh && rm ../install.sh && python3 ./setup.py"
