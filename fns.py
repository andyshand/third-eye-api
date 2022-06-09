
import io
from torch.nn import functional as F
import requests
import math
import torch
import torchvision.transforms.functional as TF
from torch.nn import functional as F
from PIL import Image, ImageOps

# https://gist.github.com/adefossez/0646dbe9ed4005480a2407c62aac8869

def get_support_fns(device, args):
  side_x = args.sizex
  side_y = args.sizey
  perlin_mode = args.perlin_mode
  batch_size = 1

  def interp(t):
      return 3 * t**2 - 2 * t**3

  def perlin(width, height, scale=10, device=None):
      gx, gy = torch.randn(2, width + 1, height + 1, 1, 1, device=device)
      xs = torch.linspace(0, 1, scale + 1)[:-1, None].to(device)
      ys = torch.linspace(0, 1, scale + 1)[None, :-1].to(device)
      wx = 1 - interp(xs)
      wy = 1 - interp(ys)
      dots = 0
      dots += wx * wy * (gx[:-1, :-1] * xs + gy[:-1, :-1] * ys)
      dots += (1 - wx) * wy * (-gx[1:, :-1] * (1 - xs) + gy[1:, :-1] * ys)
      dots += wx * (1 - wy) * (gx[:-1, 1:] * xs - gy[:-1, 1:] * (1 - ys))
      dots += (1 - wx) * (1 - wy) * (-gx[1:, 1:] * (1 - xs) - gy[1:, 1:] * (1 - ys))
      return dots.permute(0, 2, 1, 3).contiguous().view(width * scale, height * scale)

  def perlin_ms(octaves, width, height, grayscale, device):
      out_array = [0.5] if grayscale else [0.5, 0.5, 0.5]
      # out_array = [0.0] if grayscale else [0.0, 0.0, 0.0]
      for i in range(1 if grayscale else 3):
          scale = 2 ** len(octaves)
          oct_width = width
          oct_height = height
          for oct in octaves:
              p = perlin(oct_width, oct_height, scale, device)
              out_array[i] += p * oct
              scale //= 2
              oct_width *= 2
              oct_height *= 2
      return torch.cat(out_array)

  def create_perlin_noise(octaves=[1, 1, 1, 1], width=2, height=2, grayscale=True):
      out = perlin_ms(octaves, width, height, grayscale, device)
      if grayscale:
          out = TF.resize(size=(side_y, side_x), img=out.unsqueeze(0))
          out = TF.to_pil_image(out.clamp(0, 1)).convert("RGB")
      else:
          out = out.reshape(-1, 3, out.shape[0] // 3, out.shape[1])
          out = TF.resize(size=(side_y, side_x), img=out)
          out = TF.to_pil_image(out.clamp(0, 1).squeeze())

      out = ImageOps.autocontrast(out)
      return out

  def regen_perlin():
      if perlin_mode == "color":
          init = create_perlin_noise(
              [1.5**-i * 0.5 for i in range(12)], 1, 1, False
          )
          init2 = create_perlin_noise(
              [1.5**-i * 0.5 for i in range(8)], 4, 4, False
          )
      elif perlin_mode == "gray":
          init = create_perlin_noise([1.5**-i * 0.5 for i in range(12)], 1, 1, True)
          init2 = create_perlin_noise([1.5**-i * 0.5 for i in range(8)], 4, 4, True)
      else:
          init = create_perlin_noise(
              [1.5**-i * 0.5 for i in range(12)], 1, 1, False
          )
          init2 = create_perlin_noise([1.5**-i * 0.5 for i in range(8)], 4, 4, True)

      init = (
          TF.to_tensor(init)
          .add(TF.to_tensor(init2))
          .div(2)
          .to(device)
          .unsqueeze(0)
          .mul(2)
          .sub(1)
      )
      del init2
      return init.expand(batch_size, -1, -1, -1)

  def fetch(url_or_path):
      if str(url_or_path).startswith("http://") or str(url_or_path).startswith(
          "https://"
      ):
          r = requests.get(url_or_path)
          r.raise_for_status()
          fd = io.BytesIO()
          fd.write(r.content)
          fd.seek(0)
          return fd
      return open(url_or_path, "rb")

  def read_image_workaround(path):
      """OpenCV reads images as BGR, Pillow saves them as RGB. Work around
      this incompatibility to avoid colour inversions."""
      im_tmp = cv2.imread(path)
      return cv2.cvtColor(im_tmp, cv2.COLOR_BGR2RGB)

  def parse_prompt(prompt):
      if prompt.startswith("http://") or prompt.startswith("https://"):
          vals = prompt.rsplit(":", 2)
          vals = [vals[0] + ":" + vals[1], *vals[2:]]
      else:
          vals = prompt.rsplit(":", 1)
      vals = vals + ["", "1"][len(vals) :]
      return vals[0], float(vals[1])

  def sinc(x):
      return torch.where(
          x != 0, torch.sin(math.pi * x) / (math.pi * x), x.new_ones([])
      )

  def lanczos(x, a):
      cond = torch.logical_and(-a < x, x < a)
      out = torch.where(cond, sinc(x) * sinc(x / a), x.new_zeros([]))
      return out / out.sum()

  def ramp(ratio, width):
      n = math.ceil(width / ratio + 1)
      out = torch.empty([n])
      cur = 0
      for i in range(out.shape[0]):
          out[i] = cur
          cur += ratio
      return torch.cat([-out[1:].flip([0]), out])[1:-1]

  def resample(input, size, align_corners=True):
      n, c, h, w = input.shape
      dh, dw = size

      input = input.reshape([n * c, 1, h, w])

      if dh < h:
          kernel_h = lanczos(ramp(dh / h, 2), 2).to(input.device, input.dtype)
          pad_h = (kernel_h.shape[0] - 1) // 2
          input = F.pad(input, (0, 0, pad_h, pad_h), "reflect")
          input = F.conv2d(input, kernel_h[None, None, :, None])

      if dw < w:
          kernel_w = lanczos(ramp(dw / w, 2), 2).to(input.device, input.dtype)
          pad_w = (kernel_w.shape[0] - 1) // 2
          input = F.pad(input, (pad_w, pad_w, 0, 0), "reflect")
          input = F.conv2d(input, kernel_w[None, None, None, :])

      input = input.reshape([n, c, h, w])
      return F.interpolate(input, size, mode="bicubic", align_corners=align_corners)
    
  # fn_dict = {}
  # for fn in [resample, ramp, lanczos, sinc, perlin_ms, perlin, fetch, read_image_workaround, parse_prompt, regen_perlin]:
    # fn_dict[fn.__name__] = fn
    
  return resample, ramp, lanczos, sinc, perlin_ms, perlin, fetch, read_image_workaround, parse_prompt, regen_perlin
