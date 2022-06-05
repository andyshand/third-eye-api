import os
import sys
from os.path import exists as path_exists

def cmd(cmd):
    return os.system(cmd)
def clone_repo(repo_url: str):
    repo_name = repo_url.split("/")[-1].replace('.git', '')    
    if not path_exists(repo_name):
        cmd(f'git clone --depth 1 {repo_url}')
    else:
        print(f"{repo_name} already exists")
        
def install(package):
    venv_path = os.environ.get('VIRTUAL_ENV')
    major_version = sys.version_info[0]
    minor_version = sys.version_info[1]
    python_version = f"{major_version}.{minor_version}"          
    path = f"{venv_path}/lib/python{python_version}/site-packages/{package}"
    is_it_installed = path_exists(path)
    if is_it_installed:
        print(f"{package} is already installed")
    else:
        cmd(f"pip3 install {package}") 