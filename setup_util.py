import os
import sys
from os.path import exists as path_exists

def cmd(cmd):
    return os.system(cmd)
def clone_github_repo(repo_url: str):
    repo_name = repo_url.split("/")[-1].replace('.git', '')    
    if not path_exists(repo_name):
        cmd(f'git clone --depth 1 https://github.com/{repo_url}')
    else:
        print(f"{repo_name} already exists")
        
def install(package, check_name = None):
    venv_path = os.environ.get('VIRTUAL_ENV')
    major_version = sys.version_info[0]
    minor_version = sys.version_info[1]
    python_version = f"{major_version}.{minor_version}"          
    check_name = check_name if check_name else package
    path = f"{venv_path}/lib/python{python_version}/site-packages/{check_name}"
    is_it_installed = path_exists(path)
    if is_it_installed:
        print(f"{package} is already installed")
    else:
        cmd(f"pip3 install {package}") 