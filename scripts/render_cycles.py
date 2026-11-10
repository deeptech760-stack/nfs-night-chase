"""Hero-quality preset: switch an Eevee scene to Cycles on the GPU and render test frames or the animation.

blender -b scene.blend --python render_cycles.py -- --frames 60,300 --out renders/hq_ [--samples 128] [--save-as hq.blend]
blender -b scene.blend --python render_cycles.py -- --animation --out renders/frames/f_

The source .blend is never overwritten; pass --save-as to keep the Cycles version.
"""
import argparse
import sys
import time

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--frames", default="")
ap.add_argument("--animation", action="store_true")
ap.add_argument("--out", required=True)
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--percent", type=int, default=100)
ap.add_argument("--save-as", default="")
args = ap.parse_args(argv)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'

# GPU: OptiX on RTX cards, CUDA otherwise; CPU devices stay off so the GPU is not slowed down
prefs = bpy.context.preferences.addons['cycles'].preferences
used = "CPU"
for kind in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = kind
    except TypeError:
        continue
    prefs.get_devices()
    gpus = [d for d in prefs.devices if d.type == kind]
    if gpus:
        for d in prefs.devices:
            d.use = d.type == kind
        used = f"{kind}: {gpus[0].name}"
        break
c = scene.cycles
c.device = 'GPU' if used != "CPU" else 'CPU'
c.samples = args.samples
c.use_adaptive_sampling = True
c.adaptive_threshold = 0.02
c.use_denoising = True
c.denoiser = 'OPENIMAGEDENOISE'
c.denoising_use_gpu = used != "CPU"
c.max_bounces = 8
c.glossy_bounces = 4
c.transmission_bounces = 8
c.sample_clamp_indirect = 10.0  # kills fireflies from small bright lamps
c.caustics_reflective = False
c.caustics_refractive = False
scene.render.use_persistent_data = True
scene.render.use_motion_blur = True
scene.render.resolution_percentage = args.percent
print("CYCLES device", used, "samples", c.samples)


def bind_camera(f):
    for m in sorted(scene.timeline_markers, key=lambda m: m.frame):
        if m.frame <= f and m.camera:
            scene.camera = m.camera


if args.save_as:
    bpy.ops.wm.save_as_mainfile(filepath=args.save_as, copy=True)

if args.animation:
    scene.render.filepath = args.out
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    n = scene.frame_end - scene.frame_start + 1
    print("ANIMATION frames", n, "sec_per_frame", round((time.time() - t0) / n, 1))
else:
    for f in [int(x) for x in args.frames.split(",") if x]:
        scene.frame_set(f)
        bind_camera(f)
        scene.render.filepath = f"{args.out}{f:04d}.png"
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print("FRAME", f, "cam", scene.camera.name, "sec", round(time.time() - t0, 1))
