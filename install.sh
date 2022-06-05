#!/bin/bash

sudo apt-get install git ffmpeg libsm6 libxext6 curl -y
rm -rf third-eye-api
git clone --depth 1 "https://github.com/andyshand/third-eye-api.git"

source /root/venv/bin/activate
python3 -m pip install --upgrade pip
cd third-eye-api
