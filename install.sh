#!/bin/bash

sudo apt-get install git ffmpeg libsm6 libxext6 -y
rm -rf third-eye-api
git clone --depth 1 "https://github.com/andyshand/third-eye-api.git"

source /root/venv/activate
cd third-eye-api
