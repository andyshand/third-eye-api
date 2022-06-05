
import os


def cmd(cmd):
    os.system(cmd)
cmd("apt-get install -y curl")
cmd("pip install wget torch")

import pathlib
import shutil
import sys
from os.path import exists as path_exists

import torch
import wget

def clone_repo(repo_url):
    repo_name = repo_url.split("/")[-1]
    if not path_exists(repo_name):
        cmd(f'git clone --depth 1 {repo_url}')
    else:
        print(f"{repo_name} already exists")
        
cmd("pip install opencv-python")
cmd("pip install fvcore iopath lpips datetime timm ftfy")
cmd("pip install pytorch-lightning")
cmd("pip install omegaconf")
cmd("pip install einops")
cmd("pip install imageio")
cmd("pip install kornia")
cmd("pip install pathvalidate")
cmd("pip install dalle_pytorch")
pyt_version_str = torch.__version__.split("+")[0].replace(".", "")
version_str = "".join([
    f"py3{sys.version_info.minor}_cu",
    torch.version.cuda.replace(".", ""),
    f"_pyt{pyt_version_str}"
])
clone_repo("https://github.com/MSFTserver/pytorch3d-lite.git")
sys.path.append('./pytorch3d-lite')

root_path = f'.'
model_path = root_path

pathlib.Path(model_path).mkdir(parents=True, exist_ok=True)

if not (path_exists(f'{model_path}/512x512_diffusion_uncond_finetune_008100.pt')):
    wget.download(
        "https://the-eye.eu/public/AI/models/512x512_diffusion_unconditional_ImageNet/512x512_diffusion_uncond_finetune_008100.pt", model_path)
if not (path_exists(f'{model_path}/secondary_model_imagenet_2.pth')):
    wget.download(
        "https://the-eye.eu/public/AI/models/v-diffusion/secondary_model_imagenet_2.pth", model_path)
if not (path_exists(f'{model_path}/AdaBins_nyu.pt')):
    wget.download(
        "https://cloudflare-ipfs.com/ipfs/Qmd2mMnDLWePKmgfS8m6ntAg4nhV5VkUyAydYBp8cWWeB7/AdaBins_nyu.pt", model_path)
if not (path_exists(f'{model_path}/vqgan_imagenet_f16_16384.ckpt')):
    # ImageNet 16384
    cmd(f'curl -L -o "{model_path}/vqgan_imagenet_f16_16384.yaml" -C - "https://heibox.uni-heidelberg.de/d/a7530b09fed84f80a887/files/?p=%2Fconfigs%2Fmodel.yaml&dl=1"')
    # ImageNet 16384
    cmd(f'curl -L -o "{model_path}/vqgan_imagenet_f16_16384.ckpt" -C - "https://heibox.uni-heidelberg.de/d/a7530b09fed84f80a887/files/?p=%2Fckpts%2Flast.ckpt&dl=1"')
if not (path_exists(f'{model_path}/diffusion.pt')):
    cmd(f'wget -c - O "{model_path}/diffusion.pt" "https://dall-3.com/models/glid-3-xl/diffusion.pt"')
if not (path_exists(f'{model_path}/finetune.pt')):
    cmd(
        f'wget -c "https://dall-3.com/models/glid-3-xl/finetune.pt" -O "{model_path}/finetune.pt"')
if not (path_exists(f'{model_path}/bert.pt')):
    cmd(
        f'wget -c "https://dall-3.com/models/glid-3-xl/bert.pt" -O "{model_path}/bert.pt"')
if not (path_exists(f'{model_path}/kl-f8.pt')):
    cmd(
        f'wget -c https://dall-3.com/models/glid-3-xl/kl-f8.pt -O "{model_path}/kl-f8.pt"')

clone_repo("https://github.com/CompVis/taming-transformers.git")
clone_repo("https://github.com/openai/CLIP.git")
clone_repo("https://github.com/crowsonkb/guided-diffusion.git")
clone_repo("https://github.com/assafshocher/ResizeRight.git")
clone_repo("https://github.com/isl-org/MiDaS.git")
if not path_exists(f'{root_path}/MiDaS/midas_utils.py'):
    os.rename("MiDaS/utils.py", "MiDaS/midas_utils.py")
clone_repo("https://github.com/CompVis/latent-diffusion.git")
clone_repo("https://github.com/shariqfarooq123/AdaBins.git")
clone_repo("https://github.com/alembics/disco-diffusion.git")
clone_repo("https://github.com/Jack000/glid-3-xl")
if not path_exists(f'{root_path}/glid-3-xl/jack_guided_diffusion'):
    os.rename('glid-3-xl/guided_diffusion', 'glid-3-xl/jack_guided_diffusion')

if not path_exists(f'{root_path}/disco_xform_utils.py'):
    shutil.copyfile("disco-diffusion/disco_xform_utils.py",
                    "disco_xform_utils.py")
