import os
from os.path import exists as path_exists

def cmd(cmd):
    return os.system(cmd)
def clone_repo(repo_url):
    repo_name = repo_url.split("/")[-1]
    if not path_exists(repo_name):
        cmd(f'git clone --depth 1 {repo_url}')
    else:
        print(f"{repo_name} already exists")
        
def install(package):
    is_it_installed = cmd(f"pip3 show {package}")
    if is_it_installed:
        print(f"{package} is already installed")
    else:
        cmd(f"pip3 install {package}") 