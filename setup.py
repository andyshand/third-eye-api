
import os
from setup_util import cmd, install, clone_repo
from DefaultPaths import DefaultPaths

cmd("apt-get install -y curl")
cmd("pip install torch")

import pathlib
import shutil
import sys
from os.path import exists as path_exists
import torch

install("opencv-python")
cmd("pip install fvcore iopath lpips datetime timm ftfy")
install("pytorch-lightning")
install("omegaconf")
install("einops")
install("imageio")
install("kornia")
install("pathvalidate")
install("dalle_pytorch")

pyt_version_str = torch.__version__.split("+")[0].replace(".", "")
version_str = "".join([
    f"py3{sys.version_info.minor}_cu",
    torch.version.cuda.replace(".", ""),
    f"_pyt{pyt_version_str}"
])
clone_repo("https://github.com/MSFTserver/pytorch3d-lite.git")
sys.path.append('./pytorch3d-lite')

pathlib.Path(DefaultPaths.model_path).mkdir(parents=True, exist_ok=True)

def download_model(url, file_name = None):
    out_dir = DefaultPaths.model_path
    if file_name is None:
        file_name = url.split("/")[-1]
    cmd(f'`curl -L -o {out_dir}/{file_name} {url}')

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

clone_repo("https://github.com/CompVis/taming-transformers.git")
clone_repo("https://github.com/openai/CLIP.git")
clone_repo("https://github.com/crowsonkb/guided-diffusion.git")
clone_repo("https://github.com/assafshocher/ResizeRight.git")
clone_repo("https://github.com/isl-org/MiDaS.git")
if not path_exists(f'{DefaultPaths.root_path}/MiDaS/midas_utils.py'):
    os.rename("MiDaS/utils.py", "MiDaS/midas_utils.py")
clone_repo("https://github.com/CompVis/latent-diffusion.git")
clone_repo("https://github.com/shariqfarooq123/AdaBins.git")
clone_repo("https://github.com/alembics/disco-diffusion.git")
clone_repo("https://github.com/Jack000/glid-3-xl")
if not path_exists(f'{DefaultPaths.root_path}/glid-3-xl/jack_guided_diffusion'):
    os.rename('glid-3-xl/guided_diffusion', 'glid-3-xl/jack_guided_diffusion')

if not path_exists(f'{DefaultPaths.root_path}/disco_xform_utils.py'):
    shutil.copyfile("disco-diffusion/disco_xform_utils.py",
                    "disco_xform_utils.py")
