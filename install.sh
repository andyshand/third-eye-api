#!/bin/bash

sudo apt-get install git ffmpeg libsm6 libxext6 -y
git clone --depth 1 "https://github.com/andyshand/third-eye-api.git"
python3 -m venv ./venv
source ./venv/bin/activate
