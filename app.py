#!/usr/bin/env python3

from before_run import before_run
before_run()
import sys

from DefaultPaths import DefaultPaths
from SecondaryModel import alpha_sigma_to_t
from api import create_api
from fns import get_support_fns
from init_midas_depth_model import init_midas_depth_model
from load_model import load_clip_model, load_gaussian_diffusion_model, load_gaussian_diffusion_model_2, load_secondary_model, load_torch_model
# test
import gc
import math
import os
import sys
import time

from glob import glob
from os.path import exists as path_exists
from types import SimpleNamespace

import clip
import cv2
import disco_xform_utils as dxf
import lpips
import matplotlib.pyplot as plt
import pandas as pd
import py3d_tools as p3dT
import torch
import torchvision.transforms as T
import torchvision.transforms.functional as TF
from guided_diffusion.script_util import (model_and_diffusion_defaults)
from PIL import Image
from resize_right import resize
from torch import nn
from torch.nn import functional as F

# torch.cuda.empty_cache()
def run_model(generation):
    preview_image_path = f"{DefaultPaths.output_path}/preview_output.png"
    args2 = generation.args
    
    global model, diffusion
    if args2.seed is not None:
        generation.set_status(f"Setting seed to {args2.seed} ...\n")
        import numpy as np

        np.random.seed(args2.seed)
        import random

        random.seed(args2.seed)
        # next line forces deterministic random values, but causes other issues with resampling (uncomment to see)
        # torch.use_deterministic_algorithms(True)
        torch.manual_seed(args2.seed)
        torch.cuda.manual_seed(args2.seed)
        torch.cuda.manual_seed_all(args2.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    generation.set_status("Using device:", DEVICE)
    device = DEVICE  # At least one of the modules expects this name..

    # If running locally, there's a good chance your env will need this in order to not crash upon np.matmul() or similar operations.
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    # AdaBins stuff
    USE_ADABINS = True
    if USE_ADABINS:
        sys.path.append("./AdaBins")
        from infer import InferenceHelper

        MAX_ADABINS_AREA = 500000

    create_perlin_noise, resample, ramp, lanczos, sinc, perlin_ms, perlin, fetch, read_image_workaround, parse_prompt, regen_perlin = get_support_fns(device, args2)
    use_secondary_model = False
    if args2.secondarymodel == 1:
        use_secondary_model = True  # @param {type: 'boolean'}

    class MakeCutouts(nn.Module):
        def __init__(self, cut_size, cutn, skip_augs=False):
            super().__init__()
            self.cut_size = cut_size
            self.cutn = cutn
            self.skip_augs = skip_augs
            self.augs = T.Compose(
                [
                    T.RandomHorizontalFlip(p=0.5),
                    T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                    T.RandomAffine(degrees=15, translate=(0.1, 0.1)),
                    T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                    T.RandomPerspective(distortion_scale=0.4, p=0.7),
                    T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                    T.RandomGrayscale(p=0.15),
                    T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                    # T.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.1),
                ]
            )

        def forward(self, input):
            input = T.Pad(input.shape[2] // 4, fill=0)(input)
            sideY, sideX = input.shape[2:4]
            max_size = min(sideX, sideY)

            cutouts = []
            for ch in range(self.cutn):
                if ch > self.cutn - self.cutn // 4:
                    cutout = input.clone()
                else:
                    size = int(
                        max_size
                        * torch.zeros(
                            1,
                        )
                        .normal_(mean=0.8, std=0.3)
                        .clip(float(self.cut_size / max_size), 1.0)
                    )
                    offsetx = torch.randint(0, abs(sideX - size + 1), ())
                    offsety = torch.randint(0, abs(sideY - size + 1), ())
                    cutout = input[
                        :, :, offsety : offsety + size, offsetx : offsetx + size
                    ]

                if not self.skip_augs:
                    cutout = self.augs(cutout)
                cutouts.append(resample(cutout, (self.cut_size, self.cut_size)))
                del cutout

            cutouts = torch.cat(cutouts, dim=0)
            return cutouts

    cutout_debug = False
    padargs = {}

    class MakeCutoutsDango(nn.Module):
        def __init__(
            self, cut_size, Overview=4, InnerCrop=0, IC_Size_Pow=0.5, IC_Grey_P=0.2
        ):
            super().__init__()
            self.cut_size = cut_size
            self.Overview = Overview
            self.InnerCrop = InnerCrop
            self.IC_Size_Pow = IC_Size_Pow
            self.IC_Grey_P = IC_Grey_P
            if args.animation_mode == "None":
                self.augs = T.Compose(
                    [
                        T.RandomHorizontalFlip(p=0.5),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomAffine(
                            degrees=10,
                            translate=(0.05, 0.05),
                            interpolation=T.InterpolationMode.BILINEAR,
                        ),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomGrayscale(p=0.1),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.ColorJitter(
                            brightness=0.1, contrast=0.1, saturation=0.1, hue=0.1
                        ),
                    ]
                )
            elif args.animation_mode == "Video Input":
                self.augs = T.Compose(
                    [
                        T.RandomHorizontalFlip(p=0.5),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomAffine(degrees=15, translate=(0.1, 0.1)),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomPerspective(distortion_scale=0.4, p=0.7),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomGrayscale(p=0.15),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        # T.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.1),
                    ]
                )
            elif args.animation_mode == "2D" or args.animation_mode == "3D":
                self.augs = T.Compose(
                    [
                        T.RandomHorizontalFlip(p=0.4),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomAffine(
                            degrees=10,
                            translate=(0.05, 0.05),
                            interpolation=T.InterpolationMode.BILINEAR,
                        ),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.RandomGrayscale(p=0.1),
                        T.Lambda(lambda x: x + torch.randn_like(x) * 0.01),
                        T.ColorJitter(
                            brightness=0.1, contrast=0.1, saturation=0.1, hue=0.3
                        ),
                    ]
                )

        def forward(self, input):
            cutouts = []
            gray = T.Grayscale(3)
            sideY, sideX = input.shape[2:4]
            max_size = min(sideX, sideY)
            min_size = min(sideX, sideY, self.cut_size)
            l_size = max(sideX, sideY)
            output_shape = [1, 3, self.cut_size, self.cut_size]
            output_shape_2 = [1, 3, self.cut_size + 2, self.cut_size + 2]
            pad_input = F.pad(
                input,
                (
                    (sideY - max_size) // 2,
                    (sideY - max_size) // 2,
                    (sideX - max_size) // 2,
                    (sideX - max_size) // 2,
                ),
                **padargs,
            )
            cutout = resize(pad_input, out_shape=output_shape)

            if self.Overview > 0:
                if self.Overview <= 4:
                    if self.Overview >= 1:
                        cutouts.append(cutout)
                    if self.Overview >= 2:
                        cutouts.append(gray(cutout))
                    if self.Overview >= 3:
                        cutouts.append(TF.hflip(cutout))
                    if self.Overview == 4:
                        cutouts.append(gray(TF.hflip(cutout)))
                else:
                    cutout = resize(pad_input, out_shape=output_shape)
                    for _ in range(self.Overview):
                        cutouts.append(cutout)

                if cutout_debug:
                    TF.to_pil_image(cutouts[0].clamp(0, 1).squeeze(0)).save(
                        "cutout_overview0.jpg", quality=99
                    )

            if self.InnerCrop > 0:
                for i in range(self.InnerCrop):
                    size = int(
                        torch.rand([]) ** self.IC_Size_Pow * (max_size - min_size)
                        + min_size
                    )
                    offsetx = torch.randint(0, sideX - size + 1, ())
                    offsety = torch.randint(0, sideY - size + 1, ())
                    cutout = input[
                        :, :, offsety : offsety + size, offsetx : offsetx + size
                    ]
                    if i <= int(self.IC_Grey_P * self.InnerCrop):
                        cutout = gray(cutout)
                    cutout = resize(cutout, out_shape=output_shape)
                    cutouts.append(cutout)
                if cutout_debug:
                    TF.to_pil_image(cutouts[-1].clamp(0, 1).squeeze(0)).save(
                        "cutout_InnerCrop.jpg", quality=99
                    )
            cutouts = torch.cat(cutouts)
            if skip_augs is not True:
                cutouts = self.augs(cutouts)
            return cutouts

    def spherical_dist_loss(x, y):
        x = F.normalize(x, dim=-1)
        y = F.normalize(y, dim=-1)
        return (x - y).norm(dim=-1).div(2).arcsin().pow(2).mul(2)

    def tv_loss(input):
        """L2 total variation loss, as in Mahendran et al."""
        input = F.pad(input, (0, 1, 0, 1), "replicate")
        x_diff = input[..., :-1, 1:] - input[..., :-1, :-1]
        y_diff = input[..., 1:, :-1] - input[..., :-1, :-1]
        return (x_diff**2 + y_diff**2).mean([1, 2, 3])

    def range_loss(input):
        return (input - input.clamp(-1, 1)).pow(2).mean([1, 2, 3])

    stop_on_next_loop = False  # Make sure GPU memory doesn't get corrupted from cancelling the run mid-way through, allow a full frame to complete

    def do_run():
        seed = args.seed
        # generation.set_status(range(args.start_frame, args.max_frames))

        if (args.animation_mode == "3D") and (args.midas_weight > 0.0):
            (
                midas_model,
                midas_transform,
                midas_net_w,
                midas_net_h,
                midas_resize_mode,
                midas_normalization,
            ) = init_midas_depth_model(device, generation, args.midas_depth_model)
        for frame_num in range(args.start_frame, args.max_frames):
            if stop_on_next_loop:
                break

            # Print Frame progress if animation mode is on

            """
          if args.animation_mode != "None":
            batchBar = tqdm(range(args.max_frames), desc ="Frames")
            batchBar.n = frame_num
            batchBar.refresh()
          """

            # Inits if not video frames
            if args.animation_mode != "Video Input":
                if args.init_image == "":
                    init_image = None
                else:
                    init_image = args.init_image
                init_scale = args.init_scale
                skip_steps = args.skip_steps

            if args.animation_mode == "2D":
                if args.key_frames:
                    angle = args.angle_series[frame_num]
                    zoom = args.zoom_series[frame_num]
                    translation_x = args.translation_x_series[frame_num]
                    translation_y = args.translation_y_series[frame_num]
                    generation.set_status(
                        f"angle: {angle}",
                        f"zoom: {zoom}",
                        f"translation_x: {translation_x}",
                        f"translation_y: {translation_y}",
                    )

                if frame_num > 0:
                    seed = seed + 1
                    if resume_run and frame_num == start_frame:
                        img_0 = cv2.imread(
                            batchFolder
                            + f"/{batch_name}({batchNum})_{start_frame-1:04}.png"
                        )
                    else:
                        img_0 = cv2.imread("prevFrame.png")
                    center = (1 * img_0.shape[1] // 2, 1 * img_0.shape[0] // 2)
                    trans_mat = np.float32(
                        [[1, 0, translation_x], [0, 1, translation_y]]
                    )
                    rot_mat = cv2.getRotationMatrix2D(center, angle, zoom)
                    trans_mat = np.vstack([trans_mat, [0, 0, 1]])
                    rot_mat = np.vstack([rot_mat, [0, 0, 1]])
                    transformation_matrix = np.matmul(rot_mat, trans_mat)
                    img_0 = cv2.warpPerspective(
                        img_0,
                        transformation_matrix,
                        (img_0.shape[1], img_0.shape[0]),
                        borderMode=cv2.BORDER_WRAP,
                    )

                    cv2.imwrite("prevFrameScaled.png", img_0)
                    init_image = "prevFrameScaled.png"
                    init_scale = args.frames_scale
                    skip_steps = args.calc_frames_skip_steps

            if args.animation_mode == "3D":
                if args.key_frames:
                    angle = args.angle_series[frame_num]
                    # zoom = args.zoom_series[frame_num]
                    translation_x = args.translation_x_series[frame_num]
                    translation_y = args.translation_y_series[frame_num]
                    translation_z = args.translation_z_series[frame_num]
                    rotation_3d_x = args.rotation_3d_x_series[frame_num]
                    rotation_3d_y = args.rotation_3d_y_series[frame_num]
                    rotation_3d_z = args.rotation_3d_z_series[frame_num]
                    generation.set_status(
                        f"angle: {angle}",
                        # f'zoom: {zoom}',
                        f"translation_x: {translation_x}",
                        f"translation_y: {translation_y}",
                        f"translation_z: {translation_z}",
                        f"rotation_3d_x: {rotation_3d_x}",
                        f"rotation_3d_y: {rotation_3d_y}",
                        f"rotation_3d_z: {rotation_3d_z}",
                    )

                if frame_num > 0:
                    seed = seed + 1
                    img_filepath = "prevFrame.png"
                    trans_scale = 1.0 / 200.0
                    translate_xyz = [
                        -translation_x * trans_scale,
                        translation_y * trans_scale,
                        -translation_z * trans_scale,
                    ]
                    rotate_xyz = [
                        math.radians(rotation_3d_x),
                        math.radians(rotation_3d_y),
                        math.radians(rotation_3d_z),
                    ]
                    generation.set_status("translation:", translate_xyz)
                    generation.set_status("rotation:", rotate_xyz)
                    rot_mat = p3dT.euler_angles_to_matrix(
                        torch.tensor(rotate_xyz, device=device), "XYZ"
                    ).unsqueeze(0)
                    generation.set_status("rot_mat: " + str(rot_mat))
                    next_step_pil = dxf.transform_image_3d(
                        img_filepath,
                        midas_model,
                        midas_transform,
                        DEVICE,
                        rot_mat,
                        translate_xyz,
                        args.near_plane,
                        args.far_plane,
                        args.fov,
                        padding_mode=args.padding_mode,
                        sampling_mode=args.sampling_mode,
                        midas_weight=args.midas_weight,
                    )
                    next_step_pil.save("prevFrameScaled.png")

                    """
              ### Turbo mode - skip some diffusions to save time          
              if turbo_mode == True and frame_num > 10 and frame_num % int(turbo_steps) != 0:
                #turbo_steps
                generation.set_status('turbo mode is on this frame: skipping clip diffusion steps')
                #this is an even frame. copy warped prior frame w/ war 
                #filename = f'{args.batch_name}({args.batchNum})_{frame_num:04}.png'
                #next_step_pil.save(f'{batchFolder}/{filename}') #save it as this frame
                #next_step_pil.save(f'{img_filepath}') # save it also as prev_frame for next iteration
                filename = f'progress.png'
                next_step_pil.save(f'{filename}') #save it as this frame
                next_step_pil.save(f'{img_filepath}') # save it also as prev_frame for next iteration
                continue
              elif turbo_mode == True:
                generation.set_status('turbo mode is OFF this frame')
              #else: no turbo
              """

                    init_image = "prevFrameScaled.png"
                    init_scale = args.frames_scale
                    skip_steps = args.calc_frames_skip_steps

            if args.animation_mode == "Video Input":
                seed = seed + 1
                init_image = f"{videoFramesFolder}/{frame_num+1:04}.jpg"
                init_scale = args.frames_scale
                skip_steps = args.calc_frames_skip_steps

            loss_values = []

            if seed is not None:
                np.random.seed(seed)
                random.seed(seed)
                torch.manual_seed(seed)
                torch.cuda.manual_seed_all(seed)
                torch.backends.cudnn.deterministic = True

            target_embeds, weights = [], []

            if args.prompts_series is not None and frame_num >= len(
                args.prompts_series
            ):
                frame_prompt = args.prompts_series[-1]
            elif args.prompts_series is not None:
                frame_prompt = args.prompts_series[frame_num]
            else:
                frame_prompt = []

            generation.set_status(args.image_prompts_series)
            if args.image_prompts_series is not None and frame_num >= len(
                args.image_prompts_series
            ):
                image_prompt = args.image_prompts_series[-1]
            elif args.image_prompts_series is not None:
                image_prompt = args.image_prompts_series[frame_num]
            else:
                image_prompt = []

            generation.set_status(f"Frame Prompt: {frame_prompt}")

            model_stats = []
            for clip_model in clip_models:
                cutn = args2.cutn
                model_stat = {
                    "clip_model": None,
                    "target_embeds": [],
                    "make_cutouts": None,
                    "weights": [],
                }
                model_stat["clip_model"] = clip_model

                for prompt in frame_prompt:
                    txt, weight = parse_prompt(prompt)
                    txt = clip_model.encode_text(
                        clip.tokenize(prompt).to(device)
                    ).float()

                    if args.fuzzy_prompt:
                        for i in range(25):
                            model_stat["target_embeds"].append(
                                (
                                    txt + torch.randn(txt.shape).cuda() * args.rand_mag
                                ).clamp(0, 1)
                            )
                            model_stat["weights"].append(weight)
                    else:
                        model_stat["target_embeds"].append(txt)
                        model_stat["weights"].append(weight)

                if image_prompt:
                    model_stat["make_cutouts"] = MakeCutouts(
                        clip_model.visual.input_resolution, cutn, skip_augs=skip_augs
                    )
                    for prompt in image_prompt:
                        path, weight = parse_prompt(prompt)
                        img = Image.open(fetch(path)).convert("RGB")
                        img = TF.resize(
                            img,
                            min(side_x, side_y, *img.size),
                            T.InterpolationMode.LANCZOS,
                        )
                        batch = model_stat["make_cutouts"](
                            TF.to_tensor(img).to(device).unsqueeze(0).mul(2).sub(1)
                        )
                        embed = clip_model.encode_image(normalize(batch)).float()
                        if fuzzy_prompt:
                            for i in range(25):
                                model_stat["target_embeds"].append(
                                    (
                                        embed
                                        + torch.randn(embed.shape).cuda() * rand_mag
                                    ).clamp(0, 1)
                                )
                                weights.extend([weight / cutn] * cutn)
                        else:
                            model_stat["target_embeds"].append(embed)
                            model_stat["weights"].extend([weight / cutn] * cutn)

                model_stat["target_embeds"] = torch.cat(model_stat["target_embeds"])
                model_stat["weights"] = torch.tensor(
                    model_stat["weights"], device=device
                )
                if model_stat["weights"].sum().abs() < 1e-3:
                    raise RuntimeError("The weights must not sum to 0.")
                model_stat["weights"] /= model_stat["weights"].sum().abs()
                model_stats.append(model_stat)

            init = None
            if init_image is not None:
                init = Image.open(fetch(init_image)).convert("RGB")
                init = init.resize((args.side_x, args.side_y), Image.LANCZOS)
                init = TF.to_tensor(init).to(device).unsqueeze(0).mul(2).sub(1)

            if args.perlin_init:
                if args.perlin_mode == "color":
                    init = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(12)], 1, 1, False
                    )
                    init2 = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(8)], 4, 4, False
                    )
                elif args.perlin_mode == "gray":
                    init = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(12)], 1, 1, True
                    )
                    init2 = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(8)], 4, 4, True
                    )
                else:
                    init = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(12)], 1, 1, False
                    )
                    init2 = create_perlin_noise(
                        [1.5**-i * 0.5 for i in range(8)], 4, 4, True
                    )
                # init = TF.to_tensor(init).add(TF.to_tensor(init2)).div(2).to(device)
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

            cur_t = None

            def cond_fn(x, t, y=None):
                with torch.enable_grad():
                    x_is_NaN = False
                    x = x.detach().requires_grad_()
                    n = x.shape[0]
                    if use_secondary_model is True:
                        alpha = torch.tensor(
                            diffusion.sqrt_alphas_cumprod[cur_t],
                            device=device,
                            dtype=torch.float32,
                        )
                        sigma = torch.tensor(
                            diffusion.sqrt_one_minus_alphas_cumprod[cur_t],
                            device=device,
                            dtype=torch.float32,
                        )
                        cosine_t = alpha_sigma_to_t(alpha, sigma)
                        out = secondary_model(x, cosine_t[None].repeat([n])).pred
                        fac = diffusion.sqrt_one_minus_alphas_cumprod[cur_t]
                        x_in = out * fac + x * (1 - fac)
                        x_in_grad = torch.zeros_like(x_in)
                    else:
                        my_t = torch.ones([n], device=device, dtype=torch.long) * cur_t
                        out = diffusion.p_mean_variance(
                            model, x, my_t, clip_denoised=False, model_kwargs={"y": y}
                        )
                        fac = diffusion.sqrt_one_minus_alphas_cumprod[cur_t]
                        x_in = out["pred_xstart"] * fac + x * (1 - fac)
                        x_in_grad = torch.zeros_like(x_in)
                    for model_stat in model_stats:
                        for i in range(int(args.cutn_batches)):
                            t_int = (
                                int(t.item()) + 1
                            )  # errors on last step without +1, need to find source
                            # when using SLIP Base model the dimensions need to be hard coded to avoid AttributeError: 'VisionTransformer' object has no attribute 'input_resolution'
                            try:
                                input_resolution = model_stat[
                                    "clip_model"
                                ].visual.input_resolution
                            except:
                                input_resolution = 224

                            cuts = MakeCutoutsDango(
                                input_resolution,
                                Overview=args.cut_overview[1000 - t_int],
                                InnerCrop=args.cut_innercut[1000 - t_int],
                                IC_Size_Pow=args.cut_ic_pow,
                                IC_Grey_P=args.cut_icgray_p[1000 - t_int],
                            )
                            clip_in = normalize(cuts(x_in.add(1).div(2)))
                            image_embeds = (
                                model_stat["clip_model"].encode_image(clip_in).float()
                            )
                            dists = spherical_dist_loss(
                                image_embeds.unsqueeze(1),
                                model_stat["target_embeds"].unsqueeze(0),
                            )
                            dists = dists.view(
                                [
                                    args.cut_overview[1000 - t_int]
                                    + args.cut_innercut[1000 - t_int],
                                    n,
                                    -1,
                                ]
                            )
                            losses = dists.mul(model_stat["weights"]).sum(2).mean(0)
                            loss_values.append(
                                losses.sum().item()
                            )  # log loss, probably shouldn't do per cutn_batch
                            x_in_grad += (
                                torch.autograd.grad(
                                    losses.sum() * clip_guidance_scale, x_in
                                )[0]
                                / cutn_batches
                            )
                    tv_losses = tv_loss(x_in)
                    if use_secondary_model is True:
                        range_losses = range_loss(out)
                    else:
                        range_losses = range_loss(out["pred_xstart"])
                    sat_losses = torch.abs(x_in - x_in.clamp(min=-1, max=1)).mean()
                    loss = (
                        tv_losses.sum() * tv_scale
                        + range_losses.sum() * range_scale
                        + sat_losses.sum() * sat_scale
                    )
                    if init is not None and args.init_scale:
                        init_losses = lpips_model(x_in, init)
                        loss = loss + init_losses.sum() * args.init_scale
                    x_in_grad += torch.autograd.grad(loss, x_in)[0]
                    if torch.isnan(x_in_grad).any() == False:
                        grad = -torch.autograd.grad(x_in, x, x_in_grad)[0]
                    else:
                        # generation.set_status("NaN'd")
                        x_is_NaN = True
                        grad = torch.zeros_like(x)
                if args.clamp_grad and x_is_NaN == False:
                    magnitude = grad.square().mean().sqrt()
                    return (
                        grad * magnitude.clamp(max=args.clamp_max) / magnitude
                    )  # min=-0.02, min=-clamp_max,
                return grad

            if args.sampling_mode == "ddim":
                sample_fn = diffusion.ddim_sample_loop_progressive
            elif args.sampling_mode == "bicubic":
                sample_fn = diffusion.p_sample_loop_progressive
            elif args.sampling_mode == "plms":
                sample_fn = diffusion.plms_sample_loop_progressive
            # if model_config["timestep_respacing"].startswith("ddim"):
            #    sample_fn = diffusion.ddim_sample_loop_progressive
            # else:
            #    sample_fn = diffusion.p_sample_loop_progressive

            for i in range(args.n_batches):
                """
                if args.animation_mode == 'None':
                  display.clear_output(wait=True)
                  batchBar = tqdm(range(args.n_batches), desc ="Batches")
                  batchBar.n = i
                  batchBar.refresh()
                generation.set_status('')
                display.display(image_display)
                gc.collect()
                torch.cuda.empty_cache()
                """
                cur_t = diffusion.num_timesteps - skip_steps - 1
                total_steps = cur_t

                if perlin_init:
                    init = regen_perlin()

                if args.sampling_mode == "ddim":
                    samples = sample_fn(
                        model,
                        (batch_size, 3, args.side_y, args.side_x),
                        clip_denoised=clip_denoised,
                        model_kwargs={},
                        cond_fn=cond_fn,
                        progress=True,
                        skip_timesteps=skip_steps,
                        init_image=init,
                        randomize_class=randomize_class,
                        eta=eta,
                    )
                elif args.sampling_mode == "plms":
                    samples = sample_fn(
                        model,
                        (batch_size, 3, args.side_y, args.side_x),
                        clip_denoised=clip_denoised,
                        model_kwargs={},
                        cond_fn=cond_fn,
                        progress=True,
                        skip_timesteps=skip_steps,
                        init_image=init,
                        randomize_class=randomize_class,
                        order=2,
                    )
                elif args.sampling_mode == "bicubic":
                    samples = sample_fn(
                        model,
                        (batch_size, 3, args.side_y, args.side_x),
                        clip_denoised=clip_denoised,
                        model_kwargs={},
                        cond_fn=cond_fn,
                        progress=True,
                        skip_timesteps=skip_steps,
                        init_image=init,
                        randomize_class=randomize_class,
                    )

                # with run_display:
                # display.clear_output(wait=True)
                itt = 1
                imgToSharpen = None
                generation.set_status("Starting the execution...")
                gc.collect()
                torch.cuda.empty_cache()
                # from tqdm.auto import tqdm
                # from stqdm_local import stqdm

                # total_iterables = stqdm(
                #    samples, total=total_steps + 1, st_container=stoutput
                # )
                total_iterables = samples
                try:
                    j = 0
                    before_start_time = time.perf_counter()
                    for sample in total_iterables:
                        generation.set_status(f"Iteration {itt}\n")
                        cur_t -= 1
                        intermediateStep = False
                        if args.steps_per_checkpoint is not None:
                            if j % steps_per_checkpoint == 0 and j > 0:
                                intermediateStep = True
                        elif j in args.intermediate_saves:
                            intermediateStep = True
                            
                        if itt % display_rate == 0 or cur_t == -1 or itt == 1:
                            for k, image in enumerate(sample["pred_xstart"]):
                                generation.set_status("Saving progress ...\n")
                                image = TF.to_pil_image(
                                    image.add(1).div(2).clamp(0, 1)
                                )

                                if args.animation_mode != "None":
                                    generation.save_progress_image(image, "prevFrame.png")

                                generation.save_progress_image(image, preview_image_path)
                                if (args2.frame_dir is not None) and (
                                    args.animation_mode == "None"
                                ):
                                    import os

                                    file_list = []
                                    for file in sorted(os.listdir(args2.frame_dir)):
                                        if file.startswith("FRA"):
                                            if file.endswith("PNG"):
                                                if len(file) == 12:
                                                    file_list.append(file)
                                    if file_list:
                                        last_name = file_list[-1]
                                        count_value = int(last_name[3:8]) + 1
                                        count_string = f"{count_value:05d}"
                                    else:
                                        count_string = "00001"
                                    save_name = (
                                        args2.frame_dir
                                        + "/FRA"
                                        + count_string
                                        + ".PNG"
                                    )
                                    generation.save_progress_image(image, save_name)

                                # sys.stdout.flush()
                                # sys.stdout.write(f'{itt}/{args2.iterations} {skip_steps} {args.animation_mode} {args2.frame_dir}\n')
                                # sys.stdout.flush()
                                if (
                                    (args2.frame_dir is not None)
                                    and (args.animation_mode == "3D")
                                    and (itt == args2.iterations - skip_steps)
                                ):
                                    generation.set_status("Saving 3D frame ...\n")
                                    import os

                                    file_list = []
                                    for file in os.listdir(args2.frame_dir):
                                        if file.startswith("FRA"):
                                            if file.endswith("PNG"):
                                                if len(file) == 12:
                                                    file_list.append(file)
                                    if file_list:
                                        last_name = file_list[-1]
                                        count_value = int(last_name[3:8]) + 1
                                        count_string = f"{count_value:05d}"
                                    else:
                                        count_string = "00001"
                                    save_name = (
                                        args2.frame_dir
                                        + "/FRA"
                                        + count_string
                                        + ".PNG"
                                    )
                                    generation.save_progress_image(image, save_name)
                                    
                                generation.set_status("Progress saved\n")
                        itt += 1
                        j += 1
                        time_past_seconds = time.perf_counter() - before_start_time
                        iterations_per_second = j / time_past_seconds
                        time_left = (total_steps - j) / iterations_per_second
                        percentage = round((j / (total_steps + 1)) * 100)
                        
                        generation.set_progress(percentage, time_past_seconds, time_left)
                    # if path_exists(drive_path):

                except KeyboardInterrupt:
                    pass
                # except st.script_runner.StopException as e:
                #    imageLocation.image(args2.image_file)
                #    gc.collect()
                #    torch.cuda.empty_cache()
                #    generation.set_status("Done!")
                #    pass

                
                # Andy commented out the below, not sure if necessary but we
                # don't have a reference to image_display
                # with image_display:
                #     if args.sharpen_preset != "Off" and animation_mode == "None":
                #         generation.set_status("Starting Diffusion Sharpening...")
                #         do_superres(imgToSharpen, f"{batchFolder}/{filename}")

                import os
                import shutil

                from pathvalidate import sanitize_filename

                if not path_exists(DefaultPaths.output_path):
                    os.makedirs(DefaultPaths.output_path)
                save_filename = f"{DefaultPaths.output_path}/{sanitize_filename(args2.prompt)} [Disco Diffusion v5] {args2.seed}.png"
                generation.set_status(save_filename)
                file_list = []
                if path_exists(save_filename):
                    for file in sorted(os.listdir(f"{DefaultPaths.output_path}/")):
                        if file.startswith(
                            f"{sanitize_filename(args2.prompt)} [Disco Diffusion v5] {args2.seed}"
                        ):
                            generation.set_status(file)
                            file_list.append(file)
                    generation.set_status(file_list)
                    last_name = file_list[-1]
                    generation.set_status(last_name)
                    if last_name[-15:-10] == "batch":
                        count_value = int(last_name[-10:-4]) + 1
                        count_string = f"{count_value:05d}"
                        save_filename = f"{DefaultPaths.output_path}/{sanitize_filename(args2.prompt)} [Disco Diffusion v5] {args2.seed}_batch {count_string}.png"
                    else:
                        save_filename = f"{DefaultPaths.output_path}/{sanitize_filename(args2.prompt)} [Disco Diffusion v5] {args2.seed}_batch 00001.png"
                shutil.copyfile(
                    preview_image_path,
                    save_filename,
                )
                generation.done(save_filename)
                generation.set_status("Done!")
                plt.plot(np.array(loss_values), "r")
    

    # 2. Diffusion and CLIP model settings"""

    if args2.use256 == 0:
        generation.set_status("Loading 512x512_diffusion_uncond_finetune_008100 ...\n")
        diffusion_model = "512x512_diffusion_uncond_finetune_008100"  # @param ["256x256_diffusion_uncond", "512x512_diffusion_uncond_finetune_008100"]
    else:
        generation.set_status("Loading 256x256_diffusion_uncond ...\n")
        diffusion_model = "256x256_diffusion_uncond"


    # timestep_respacing = '50' # param ['25','50','100','150','250','500','1000','ddim25','ddim50', 'ddim75', 'ddim100','ddim150','ddim250','ddim500','ddim1000']
    if args2.sampling_mode == "ddim" or args2.sampling_mode == "plms":
        timestep_respacing = "ddim" + str(
            args2.iterations
        )  #'ddim100' # Modify this value to decrease the number of timesteps.
    else:
        timestep_respacing = str(
            args2.iterations
        )  #'ddim100' # Modify this value to decrease the number of timesteps.

    diffusion_steps = 1000  # param {type: 'number'}
    use_checkpoint = True  # @param {type: 'boolean'}

    model_config = model_and_diffusion_defaults()
    if diffusion_model == "512x512_diffusion_uncond_finetune_008100":
        model_config.update(
            {
                "attention_resolutions": "32, 16, 8",
                "class_cond": False,
                "diffusion_steps": diffusion_steps,
                "rescale_timesteps": True,
                "timestep_respacing": timestep_respacing,
                "image_size": 512,
                "learn_sigma": True,
                "noise_schedule": "linear",
                "num_channels": 256,
                "num_head_channels": 64,
                "num_res_blocks": 2,
                "resblock_updown": True,
                "use_checkpoint": use_checkpoint,
                "use_fp16": True,
                "use_scale_shift_norm": True,
            }
        )
    elif diffusion_model == "256x256_diffusion_uncond":
        model_config.update(
            {
                "attention_resolutions": "32, 16, 8",
                "class_cond": False,
                "diffusion_steps": diffusion_steps,
                "rescale_timesteps": True,
                "timestep_respacing": timestep_respacing,
                "image_size": 256,
                "learn_sigma": True,
                "noise_schedule": "linear",
                "num_channels": 256,
                "num_head_channels": 64,
                "num_res_blocks": 2,
                "resblock_updown": True,
                "use_checkpoint": use_checkpoint,
                "use_fp16": True,
                "use_scale_shift_norm": True,
            }
        )

    model_default = model_config["image_size"]

    secondary_model = load_secondary_model(device, generation)
    
    clip_models = []
    model_map = {
        "ViT-B/32": "usevit32",
        "ViT-B/16": "usevit16",
        "ViT-L/14": "usevit14",
        "RN50x4": "usern50x4",
        "RN50x16": "usern50x16",
        "RN50x64": "usern50x64",
        "RN50": "usern50",
        "RN101": "usern101",    
    }
    
    # Load required models
    for key in model_map:
        flag = model_map[key]
        if getattr(args2, flag) == 1:
            clip_models.append(load_clip_model(key, device, generation))
            
    normalize = T.Normalize(
        mean=[0.48145466, 0.4578275, 0.40821073],
        std=[0.26862954, 0.26130258, 0.27577711],
    )
    generation.set_status("Loading lpips model...\n")
    lpips_model = lpips.LPIPS(net="vgg").to(device)

    """# 3. Settings"""
    
    # @markdown ####**Basic Settings:**
    batch_name = "TimeToDisco"  # @param{type: 'string'}
    steps = (
        args2.iterations
    )  # @param [25,50,100,150,250,500,1000]{type: 'raw', allow-input: true}
    width_height = [args2.sizex, args2.sizey]  # @param{type: 'raw'}
    clip_guidance_scale = args2.guidancescale  # @param{type: 'number'}
    tv_scale = args2.tvscale  # @param{type: 'number'}
    range_scale = args2.rangescale  # @param{type: 'number'}
    sat_scale = args2.saturationscale  # @param{type: 'number'}
    cutn_batches = args2.cutnbatches  # @param{type: 'number'}

    if args2.useaugs == 1:
        skip_augs = False  # False - Controls whether to skip torchvision augmentations
    else:
        skip_augs = True  # False - Controls whether to skip torchvision augmentations

    # @markdown ####**Init Settings:**
    if args2.seed_image is not None:
        init_image = (
            args2.seed_image
        )  # This can be an URL or Colab local path and must be in quotes.
        skip_steps = (
            args2.skipseedtimesteps
        )  # 12 Skip unstable steps                  # Higher values make the output look more like the init.
        init_scale = (
            args2.initscale
        )  # This enhances the effect of the init image, a good value is 1000.
    else:
        init_image = ""  # This can be an URL or Colab local path and must be in quotes.
        skip_steps = 0  # 12 Skip unstable steps                  # Higher values make the output look more like the init.
        init_scale = (
            0  # This enhances the effect of the init image, a good value is 1000.
        )

    if init_image == "":
        init_image = None

    side_x = args2.sizex
    side_y = args2.sizey

    # Update Model Settings
    # timestep_respacing = f'ddim{steps}'
    diffusion_steps = (1000 // steps) * steps if steps < 1000 else steps
    model_config.update(
        {
            "timestep_respacing": timestep_respacing,
            "diffusion_steps": diffusion_steps,
        }
    )

    # Make folder for batch
    batchFolder = f"./"
    # createPath(batchFolder)

    """###Animation Settings"""

    # @markdown ####**Animation Mode:**
    animation_mode = (
        args2.animation_mode
    )  #'None' #@param ['None', '2D', '3D', 'Video Input'] {type:'string'}
    # @markdown *For animation, you probably want to turn `cutn_batches` to 1 to make it quicker.*

    # @markdown ---

    # @markdown ####**Video Input Settings:**
    video_init_path = "training.mp4"  # "D:\\sample_cat.mp4" #@param {type: 'string'}
    extract_nth_frame = 2  # @param {type:"number"}

    if animation_mode == "Video Input":
        videoFramesFolder = "./videoFrames"
        # createPath(videoFramesFolder)
        # generation.set_status(f"Exporting Video Frames (1 every {extract_nth_frame})...")
        generation.set_status(f"Exporting Video Frames (1 every {extract_nth_frame})...\n")

        """
      try:
        !rm {videoFramesFolder}/*.jpg
      except:
        generation.set_status('')
      """
        vf = f'"select=not(mod(n\,{extract_nth_frame}))"'
        os.system(
            f"ffmpeg.exe -i {video_init_path} -vf {vf} -vsync vfr -q:v 2 -loglevel error -stats {videoFramesFolder}/%04d.jpg"
        )

    # @markdown ---

    # @markdown ####**2D Animation Settings:**
    # @markdown `zoom` is a multiplier of dimensions, 1 is no zoom.

    key_frames = True  # @param {type:"boolean"}
    max_frames = args2.max_frames  # 10000#@param {type:"number"}

    if animation_mode == "Video Input":
        max_frames = len(glob(f"{videoFramesFolder}/*.jpg"))


    interp_spline = "Linear"  # Do not change, currently will not look good. param ['Linear','Quadratic','Cubic']{type:"string"}
    angle = args2.angle  # "0:(0)"#@param {type:"string"}
    zoom = args2.zoom  # "0: (1), 10: (1.05)"#@param {type:"string"}
    translation_x = args2.translation_x  # "0: (0)"#@param {type:"string"}
    translation_y = args2.translation_y  # "0: (0)"#@param {type:"string"}
    translation_z = args2.translation_z  # "0: (10.0)"#@param {type:"string"}
    rotation_3d_x = args2.rotation_3d_x  # "0: (0)"#@param {type:"string"}
    rotation_3d_y = args2.rotation_3d_y  # "0: (0)"#@param {type:"string"}
    rotation_3d_z = args2.rotation_3d_z  # "0: (0)"#@param {type:"string"}
    midas_depth_model = "dpt_large"  # @param {type:"string"}
    midas_weight = args2.midas_weight  # 0.3#@param {type:"number"}
    near_plane = args2.near_plane  # 200#@param {type:"number"}
    far_plane = args2.far_plane  # 10000#@param {type:"number"}
    fov = args2.fov  # 40#@param {type:"number"}
    padding_mode = "border"  # @param {type:"string"}
    sampling_mode = args2.sampling_mode  # @param {type:"string"}
    # @markdown ####**Coherency Settings:**
    # @markdown `frame_scale` tries to guide the new frame to looking like the old one. A good default is 1500.
    frames_scale = args2.frames_scale  # 1500 #@param{type: 'integer'}
    # @markdown `frame_skip_steps` will blur the previous frame - higher values will flicker less but struggle to add enough new detail to zoom into.
    frames_skip_steps = (
        args2.frames_skip_steps
    )  #'60%' #@param ['40%', '50%', '60%', '70%', '80%'] {type: 'string'}

    if args2.turbo_mode == 1:
        turbo_mode = True  # @param {type:"boolean"}
    else:
        turbo_mode = False  # @param {type:"boolean"}
    turbo_steps = args2.turbo_steps  # "3" #@param ["2","3","4"] {type:'string'}
    # @markdown ---

    def parse_key_frames(string, prompt_parser=None):
        """Given a string representing frame numbers paired with parameter values at that frame,
        return a dictionary with the frame numbers as keys and the parameter values as the values.

        Parameters
        ----------
        string: string
            Frame numbers paired with parameter values at that frame number, in the format
            'framenumber1: (parametervalues1), framenumber2: (parametervalues2), ...'
        prompt_parser: function or None, optional
            If provided, prompt_parser will be applied to each string of parameter values.

        Returns
        -------
        dict
            Frame numbers as keys, parameter values at that frame number as values

        Raises
        ------
        RuntimeError
            If the input string does not match the expected format.

        Examples
        --------
        >>> parse_key_frames("10:(Apple: 1| Orange: 0), 20: (Apple: 0| Orange: 1| Peach: 1)")
        {10: 'Apple: 1| Orange: 0', 20: 'Apple: 0| Orange: 1| Peach: 1'}

        >>> parse_key_frames("10:(Apple: 1| Orange: 0), 20: (Apple: 0| Orange: 1| Peach: 1)", prompt_parser=lambda x: x.lower()))
        {10: 'apple: 1| orange: 0', 20: 'apple: 0| orange: 1| peach: 1'}
        """
        import re

        pattern = r"((?P<frame>[0-9]+):[\s]*[\(](?P<param>[\S\s]*?)[\)])"
        frames = dict()
        for match_object in re.finditer(pattern, string):
            frame = int(match_object.groupdict()["frame"])
            param = match_object.groupdict()["param"]
            if prompt_parser:
                frames[frame] = prompt_parser(param)
            else:
                frames[frame] = param

        if frames == {} and len(string) != 0:
            raise RuntimeError("Key Frame string not correctly formatted")
        return frames

    def get_inbetweens(key_frames, integer=False):
        """Given a dict with frame numbers as keys and a parameter value as values,
        return a pandas Series containing the value of the parameter at every frame from 0 to max_frames.
        Any values not provided in the input dict are calculated by linear interpolation between
        the values of the previous and next provided frames. If there is no previous provided frame, then
        the value is equal to the value of the next provided frame, or if there is no next provided frame,
        then the value is equal to the value of the previous provided frame. If no frames are provided,
        all frame values are NaN.

        Parameters
        ----------
        key_frames: dict
            A dict with integer frame numbers as keys and numerical values of a particular parameter as values.
        integer: Bool, optional
            If True, the values of the output series are converted to integers.
            Otherwise, the values are floats.

        Returns
        -------
        pd.Series
            A Series with length max_frames representing the parameter values for each frame.

        Examples
        --------
        >>> max_frames = 5
        >>> get_inbetweens({1: 5, 3: 6})
        0    5.0
        1    5.0
        2    5.5
        3    6.0
        4    6.0
        dtype: float64

        >>> get_inbetweens({1: 5, 3: 6}, integer=True)
        0    5
        1    5
        2    5
        3    6
        4    6
        dtype: int64
        """
        key_frame_series = pd.Series([np.nan for a in range(max_frames)])

        for i, value in key_frames.items():
            key_frame_series[i] = value
        key_frame_series = key_frame_series.astype(float)

        interp_method = interp_spline

        if interp_method == "Cubic" and len(key_frames.items()) <= 3:
            interp_method = "Quadratic"

        if interp_method == "Quadratic" and len(key_frames.items()) <= 2:
            interp_method = "Linear"

        key_frame_series[0] = key_frame_series[key_frame_series.first_valid_index()]
        key_frame_series[max_frames - 1] = key_frame_series[
            key_frame_series.last_valid_index()
        ]
        # key_frame_series = key_frame_series.interpolate(method=intrp_method,order=1, limit_direction='both')
        key_frame_series = key_frame_series.interpolate(
            method=interp_method.lower(), limit_direction="both"
        )
        if integer:
            return key_frame_series.astype(int)
        return key_frame_series

    def split_prompts(prompts):
        prompt_series = pd.Series([np.nan for a in range(max_frames)])
        for i, prompt in prompts.items():
            prompt_series[i] = prompt
        # prompt_series = prompt_series.astype(str)
        prompt_series = prompt_series.ffill().bfill()
        return prompt_series

    if key_frames:
        try:
            angle_series = get_inbetweens(parse_key_frames(angle))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `angle` correctly for key frames.\n"
                "Attempting to interpret `angle` as "
                f'"0: ({angle})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            angle = f"0: ({angle})"
            angle_series = get_inbetweens(parse_key_frames(angle))

        try:
            zoom_series = get_inbetweens(parse_key_frames(zoom))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `zoom` correctly for key frames.\n"
                "Attempting to interpret `zoom` as "
                f'"0: ({zoom})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            zoom = f"0: ({zoom})"
            zoom_series = get_inbetweens(parse_key_frames(zoom))

        try:
            translation_x_series = get_inbetweens(parse_key_frames(translation_x))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `translation_x` correctly for key frames.\n"
                "Attempting to interpret `translation_x` as "
                f'"0: ({translation_x})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            translation_x = f"0: ({translation_x})"
            translation_x_series = get_inbetweens(parse_key_frames(translation_x))

        try:
            translation_y_series = get_inbetweens(parse_key_frames(translation_y))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `translation_y` correctly for key frames.\n"
                "Attempting to interpret `translation_y` as "
                f'"0: ({translation_y})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            translation_y = f"0: ({translation_y})"
            translation_y_series = get_inbetweens(parse_key_frames(translation_y))

        try:
            translation_z_series = get_inbetweens(parse_key_frames(translation_z))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `translation_z` correctly for key frames.\n"
                "Attempting to interpret `translation_z` as "
                f'"0: ({translation_z})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            translation_z = f"0: ({translation_z})"
            translation_z_series = get_inbetweens(parse_key_frames(translation_z))

        try:
            rotation_3d_x_series = get_inbetweens(parse_key_frames(rotation_3d_x))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `rotation_3d_x` correctly for key frames.\n"
                "Attempting to interpret `rotation_3d_x` as "
                f'"0: ({rotation_3d_x})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            rotation_3d_x = f"0: ({rotation_3d_x})"
            rotation_3d_x_series = get_inbetweens(parse_key_frames(rotation_3d_x))

        try:
            rotation_3d_y_series = get_inbetweens(parse_key_frames(rotation_3d_y))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `rotation_3d_y` correctly for key frames.\n"
                "Attempting to interpret `rotation_3d_y` as "
                f'"0: ({rotation_3d_y})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            rotation_3d_y = f"0: ({rotation_3d_y})"
            rotation_3d_y_series = get_inbetweens(parse_key_frames(rotation_3d_y))

        try:
            rotation_3d_z_series = get_inbetweens(parse_key_frames(rotation_3d_z))
        except RuntimeError as e:
            generation.set_status(
                "WARNING: You have selected to use key frames, but you have not "
                "formatted `rotation_3d_z` correctly for key frames.\n"
                "Attempting to interpret `rotation_3d_z` as "
                f'"0: ({rotation_3d_z})"\n'
                "Please read the instructions to find out how to use key frames "
                "correctly.\n"
            )
            rotation_3d_z = f"0: ({rotation_3d_z})"
            rotation_3d_z_series = get_inbetweens(parse_key_frames(rotation_3d_z))

    else:
        angle = float(angle)
        zoom = float(zoom)
        translation_x = float(translation_x)
        translation_y = float(translation_y)
        translation_z = float(translation_z)
        rotation_3d_x = float(rotation_3d_x)
        rotation_3d_y = float(rotation_3d_y)
        rotation_3d_z = float(rotation_3d_z)

    """### Extra Settings
     Partial Saves, Diffusion Sharpening, Advanced Settings, Cutn Scheduling
    """

    # @markdown ####**Saving:**

    intermediate_saves = 0  # @param{type: 'raw'}
    intermediates_in_subfolder = True  # @param{type: 'boolean'}
    # @markdown Intermediate steps will save a copy at your specified intervals. You can either format it as a single integer or a list of specific steps

    # @markdown A value of `2` will save a copy at 33% and 66%. 0 will save none.

    # @markdown A value of `[5, 9, 34, 45]` will save at steps 5, 9, 34, and 45. (Make sure to include the brackets)

    if type(intermediate_saves) is not list:
        if intermediate_saves:
            steps_per_checkpoint = math.floor(
                (steps - skip_steps - 1) // (intermediate_saves + 1)
            )
            steps_per_checkpoint = (
                steps_per_checkpoint if steps_per_checkpoint > 0 else 1
            )
            generation.set_status(f"Will save every {steps_per_checkpoint} steps")
        else:
            steps_per_checkpoint = steps + 10
    else:
        steps_per_checkpoint = None

    if intermediate_saves and intermediates_in_subfolder is True:
        partialFolder = f"{batchFolder}/partials"
        createPath(partialFolder)

        # @markdown ---

    # @markdown ####**SuperRes Sharpening:**
    # @markdown *Sharpen each image using latent-diffusion. Does not run in animation mode. `keep_unsharp` will save both versions.*
    sharpen_preset = "Off"  # @param ['Off', 'Faster', 'Fast', 'Slow', 'Very Slow']
    keep_unsharp = True  # @param{type: 'boolean'}

    if sharpen_preset != "Off" and keep_unsharp is True:
        unsharpenFolder = f"{batchFolder}/unsharpened"
        createPath(unsharpenFolder)

        # @markdown ---

    # @markdown ####**Advanced Settings:**
    # @markdown *There are a few extra advanced settings available if you double click this cell.*

    # @markdown *Perlin init will replace your init, so uncheck if using one.*

    if args2.perlin_init == 1:
        perlin_init = True  # @param{type: 'boolean'}
    else:
        perlin_init = False  # @param{type: 'boolean'}
    perlin_mode = args2.perlin_mode  #'mixed' #@param ['mixed', 'color', 'gray']

    set_seed = "random_seed"  # @param{type: 'string'}
    eta = args2.eta  # @param{type: 'number'}
    clamp_grad = True  # @param{type: 'boolean'}
    clamp_max = args2.clampmax  # @param{type: 'number'}

    ### EXTRA ADVANCED SETTINGS:
    randomize_class = True
    if args2.denoised == 1:
        clip_denoised = True
    else:
        clip_denoised = False
    fuzzy_prompt = False
    rand_mag = 0.05

    # @markdown ---

    # @markdown ####**Cutn Scheduling:**
    # @markdown Format: `[40]*400+[20]*600` = 40 cuts for the first 400 /1000 steps, then 20 for the last 600/1000

    # @markdown cut_overview and cut_innercut are cumulative for total cutn on any given step. Overview cuts see the entire image and are good for early structure, innercuts are your standard cutn.

    cut_overview = "[12]*400+[4]*600"  # @param {type: 'string'}
    cut_innercut = "[4]*400+[12]*600"  # @param {type: 'string'}
    cut_ic_pow = 1  # @param {type: 'number'}
    cut_icgray_p = "[0.2]*400+[0]*600"  # @param {type: 'string'}

    """###Prompts
    `animation_mode: None` will only use the first set. `animation_mode: 2D / Video` will run through them per the set frames and hold on the last one.
    """

    """
    text_prompts = {
        0: ["A beautiful painting of a singular lighthouse, shining its light across a tumultuous sea of blood by greg rutkowski and thomas kinkade, Trending on artstation.", "yellow color scheme"],
        100: ["This set of prompts start at frame 100","This prompt has weight five:5"],
    }
    """

    text_prompts = {0: [phrase.strip() for phrase in args2.prompt.split("|")]}

    image_prompts = {
        # 0:['ImagePromptsWorkButArentVeryGood.png:2',],
    }

    """# 4. Diffuse!"""

    # @title Do the Run!
    # @markdown `n_batches` ignored with animation modes.
    display_rate = 5  # @param{type: 'number'}
    n_batches = 1  # @param{type: 'number'}

    batch_size = 1

    def move_files(start_num, end_num, old_folder, new_folder):
        for i in range(start_num, end_num):
            old_file = old_folder + f"/{batch_name}({batchNum})_{i:04}.png"
            new_file = new_folder + f"/{batch_name}({batchNum})_{i:04}.png"
            os.rename(old_file, new_file)

    # @markdown ---

    resume_run = False  # @param{type: 'boolean'}
    run_to_resume = "latest"  # @param{type: 'string'}
    resume_from_frame = "latest"  # @param{type: 'string'}
    retain_overwritten_frames = False  # @param{type: 'boolean'}
    if retain_overwritten_frames is True:
        retainFolder = f"{batchFolder}/retained"
        createPath(retainFolder)

    skip_step_ratio = int(frames_skip_steps.rstrip("%")) / 100
    calc_frames_skip_steps = math.floor(steps * skip_step_ratio)

    if steps <= calc_frames_skip_steps:
        sys.exit("ERROR: You can't skip more steps than your total steps")

    start_frame = 0
    batchNum = 1

    if set_seed == "random_seed":
        random.seed()
        seed = random.randint(0, 2**32)
        # generation.set_status(f'Using seed: {seed}')
    else:
        seed = int(set_seed)

    args = {
        "batchNum": batchNum,
        "prompts_series": split_prompts(text_prompts) if text_prompts else None,
        "image_prompts_series": split_prompts(image_prompts) if image_prompts else None,
        "seed": seed,
        "display_rate": display_rate,
        "n_batches": n_batches if animation_mode == "None" else 1,
        "batch_size": batch_size,
        "batch_name": batch_name,
        "steps": steps,
        "width_height": width_height,
        "clip_guidance_scale": clip_guidance_scale,
        "tv_scale": tv_scale,
        "range_scale": range_scale,
        "sat_scale": sat_scale,
        "cutn_batches": cutn_batches,
        "init_image": init_image,
        "init_scale": init_scale,
        "skip_steps": skip_steps,
        "sharpen_preset": sharpen_preset,
        "keep_unsharp": keep_unsharp,
        "side_x": side_x,
        "side_y": side_y,
        "timestep_respacing": timestep_respacing,
        "diffusion_steps": diffusion_steps,
        "animation_mode": animation_mode,
        "video_init_path": video_init_path,
        "extract_nth_frame": extract_nth_frame,
        "key_frames": key_frames,
        "max_frames": max_frames if animation_mode != "None" else 1,
        "interp_spline": interp_spline,
        "start_frame": start_frame,
        "angle": angle,
        "zoom": zoom,
        "translation_x": translation_x,
        "translation_y": translation_y,
        "translation_z": translation_z,
        "rotation_3d_x": rotation_3d_x,
        "rotation_3d_y": rotation_3d_y,
        "rotation_3d_z": rotation_3d_z,
        "midas_depth_model": midas_depth_model,
        "midas_weight": midas_weight,
        "near_plane": near_plane,
        "far_plane": far_plane,
        "fov": fov,
        "padding_mode": padding_mode,
        "sampling_mode": sampling_mode,
        "angle_series": angle_series,
        "zoom_series": zoom_series,
        "translation_x_series": translation_x_series,
        "translation_y_series": translation_y_series,
        "translation_z_series": translation_z_series,
        "rotation_3d_x_series": rotation_3d_x_series,
        "rotation_3d_y_series": rotation_3d_y_series,
        "rotation_3d_z_series": rotation_3d_z_series,
        "frames_scale": frames_scale,
        "calc_frames_skip_steps": calc_frames_skip_steps,
        "skip_step_ratio": skip_step_ratio,
        "calc_frames_skip_steps": calc_frames_skip_steps,
        "text_prompts": text_prompts,
        "image_prompts": image_prompts,
        "cut_overview": eval(cut_overview),
        "cut_innercut": eval(cut_innercut),
        "cut_ic_pow": cut_ic_pow,
        "cut_icgray_p": eval(cut_icgray_p),
        "intermediate_saves": intermediate_saves,
        "intermediates_in_subfolder": intermediates_in_subfolder,
        "steps_per_checkpoint": steps_per_checkpoint,
        "perlin_init": perlin_init,
        "perlin_mode": perlin_mode,
        "set_seed": set_seed,
        "eta": eta,
        "clamp_grad": clamp_grad,
        "clamp_max": clamp_max,
        "skip_augs": skip_augs,
        "randomize_class": randomize_class,
        "clip_denoised": clip_denoised,
        "fuzzy_prompt": fuzzy_prompt,
        "rand_mag": rand_mag,
    }

    args = SimpleNamespace(**args)

    generation.set_status("Prepping model...")
    try:
        diffusion = load_gaussian_diffusion_model(model_config, generation)
    except:
        load_gaussian_diffusion_model_2(diffusion_model, model_config, device, generation)
    
    generation.set_status(f"Starting ...\n")
    gc.collect()
    # torch.cuda.empty_cache()
    try:
        do_run()
    # except st.script_runner.StopException as e:
    #    generation.set_status("stopped here (a bit out)")
    #    pass
    except KeyboardInterrupt:
        pass
    finally:
        gc.collect()
        # torch.cuda.empty_cache()

create_api(run_model)