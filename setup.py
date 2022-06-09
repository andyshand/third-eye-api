#!/usr/bin/env python3

import os
import pathlib
import shutil
import sys
from os.path import exists as path_exists

from DefaultPaths import DefaultPaths
from add_to_path import add_to_path
from setup_util import clone_github_repo, cmd, install

install("torch")
import torch

install('munch')
install('matplotlib')
install("opencv-python", "cv2")
install("pandas")
for mod in 'fvcore iopath lpips datetime timm ftfy'.split():
    install(mod)
install("pytorch-lightning")
install("pathvalidate")
install("dalle_pytorch")
install("flask")

pyt_version_str = torch.__version__.split("+")[0].replace(".", "")
version_str = "".join([
    f"py3{sys.version_info.minor}_cu",
    torch.version.cuda.replace(".", ""),
    f"_pyt{pyt_version_str}"
])
clone_github_repo("MSFTserver/pytorch3d-lite.git")
add_to_path('./pytorch3d-lite')

pathlib.Path(DefaultPaths.model_path).mkdir(parents=True, exist_ok=True)

def download_model(url, file_name = None):
    out_dir = DefaultPaths.model_path
    if file_name is None:
        file_name = url.split("/")[-1]
    if path_exists(f"{out_dir}/{file_name}"):
        print(f"{file_name} already exists")
    else: 
        print(f"Downloading {url}")
        cmd(f'curl -L --progress-bar -o {out_dir}/{file_name} {url}')

download_model("https://the-eye.eu/public/AI/models/512x512_diffusion_unconditional_ImageNet/512x512_diffusion_uncond_finetune_008100.pt")
download_model("https://the-eye.eu/public/AI/models/v-diffusion/secondary_model_imagenet_2.pth")
download_model("https://cloudflare-ipfs.com/ipfs/Qmd2mMnDLWePKmgfS8m6ntAg4nhV5VkUyAydYBp8cWWeB7/AdaBins_nyu.pt")
    
# ImageNet 16384
download_model("https://heibox.uni-heidelberg.de/d/a7530b09fed84f80a887/files/?p=%2Fconfigs%2Fmodel.yaml&dl=1", "vqgan_imagenet_f16_16384.yaml");
download_model("https://heibox.uni-heidelberg.de/d/a7530b09fed84f80a887/files/?p=%2Fconfigs%2Flast.ckpt&dl=1", "vqgan_imagenet_f16_16384.ckpt");

download_model("https://dall-3.com/models/glid-3-xl/diffusion.pt");
download_model("https://dall-3.com/models/glid-3-xl/finetune.pt");
download_model("https://dall-3.com/models/glid-3-xl/bert.pt");
download_model("https://dall-3.com/models/glid-3-xl/kl-f8.pt");

clone_github_repo("CompVis/taming-transformers.git")
clone_github_repo("openai/CLIP.git")
clone_github_repo("crowsonkb/guided-diffusion.git")
clone_github_repo("assafshocher/ResizeRight.git")
clone_github_repo("isl-org/MiDaS.git")
if not path_exists(f'{DefaultPaths.root_path}/MiDaS/midas_utils.py'):
    os.rename("MiDaS/utils.py", "MiDaS/midas_utils.py")
clone_github_repo("CompVis/latent-diffusion.git")
clone_github_repo("shariqfarooq123/AdaBins.git")
clone_github_repo("alembics/disco-diffusion.git")
clone_github_repo("Jack000/glid-3-xl")
if not path_exists(f'{DefaultPaths.root_path}/glid-3-xl/jack_guided_diffusion'):
    os.rename('glid-3-xl/guided_diffusion', 'glid-3-xl/jack_guided_diffusion')

if not path_exists(f'{DefaultPaths.root_path}/disco_xform_utils.py'):
    shutil.copyfile("disco-diffusion/disco_xform_utils.py",
                    "disco_xform_utils.py")
