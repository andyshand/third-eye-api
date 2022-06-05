from add_to_path import add_to_path

def before_run():
  for path in '. ResizeRight MiDaS CLIP guided-diffusion latent-diffusion taming-transformers disco-diffusion AdaBins pytorch3d-lite'.split():
      add_to_path(path)

      