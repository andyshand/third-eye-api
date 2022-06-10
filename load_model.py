from DefaultPaths import DefaultPaths
from SecondaryModel import SecondaryDiffusionImageNet2
import clip
from guided_diffusion.script_util import (create_gaussian_diffusion,
                                          create_model_and_diffusion,
                                          model_and_diffusion_defaults)
import torch
loaded_models = {}

def load_or_cached(key, create, generation):
  if key not in loaded_models:
    generation.set_status(f'Loading {key}')
    loaded_models[key] = create()
  else:
    generation.set_status(f'Using cached {key}')
  return loaded_models[key]

def load_clip_model(model, device, generation):
  def create():
    return clip.load(model, jit=False)[0].eval().requires_grad_(False).to(device)  
  return load_or_cached(model, create, generation)
  
def load_torch_model(model, location, generation):
  def create():
    return torch.load(model, map_location=location)
  return load_or_cached(model, create, generation)

def load_gaussian_diffusion_model(model_config, generation):
  global diffusion  
  def create():
    return create_gaussian_diffusion(**model_config)
  diffusion = load_or_cached("gaussian_diffusion", create, generation)

# Was previous in an 'except' block, fallback for above method afaik
def load_gaussian_diffusion_model_2(diffusion_model, model_config, device, generation):
  global diffusion, model
  def create():
    model, diffusion = create_model_and_diffusion(**model_config)
    model.load_state_dict(load_torch_model(f"{DefaultPaths.model_path}/{diffusion_model}.pt", "cpu"))
    model.requires_grad_(False).eval().to(device)
    for name, param in model.named_parameters():
        if "qkv" in name or "norm" in name or "proj" in name:
            param.requires_grad_()
    if model_config["use_fp16"]:
        model.convert_to_fp16()

  model, diffusion = load_or_cached("gaussian_diffusion_2", create, generation)

def load_secondary_model(device, generation):
  def create():
    secondary_model = SecondaryDiffusionImageNet2()
    secondary_model.load_state_dict(
        torch.load(
            f"{DefaultPaths.model_path}/secondary_model_imagenet_2.pth",
            map_location="cpu",
        )
    )
    secondary_model.eval().requires_grad_(False).to(device)
  return load_or_cached("Secondary model", create, generation)
  
  