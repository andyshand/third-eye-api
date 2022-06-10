#!/bin/bash

# Check we're in the user's home directory
if [ ! -d "$HOME" ]; then
  read -p "Are you sure you want to run this outside of the home directory? [y/N] " -n 1 -r
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# Remove existing repo
rm -rf third-eye-api

# Dependencies for everything
sudo apt-get install git ffmpeg libsm6 libxext6 curl -y

# Check if node is installed
if ! [ -x "$(command -v node)" ]; then
  # Install node via nvm, so we can install `degit` to quickly clone git repos
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                   # This loads nvm
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion" # This loads nvm bash_completion
  nvm install 16
fi

npm i -g degit nodemon

# The only git repo where we're interested in the git history
git clone --depth 1 "https://github.com/andyshand/third-eye-api.git"

source /root/venv/bin/activate
python3 -m pip install --upgrade pip
cd third-eye-api

./setup.py
