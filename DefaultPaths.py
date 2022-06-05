
import os
from os.path import exists as path_exists
home_path = os.environ.get('HOME')

class DefaultPaths:
    root_path = f"."
    is_drive = False
    model_path = f"{home_path}/models"
    output_path = f"{root_path}/outputs"
