import os
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
    python_version = os.environ.get('PYTHON_VERSION')
    is_it_installed = path_exists(f'{venv_path}/lib/python{python_version}/site-packages/{package}')
    if is_it_installed:
        print(f"{package} is already installed")
    else:
        cmd(f"pip3 install {package}") 