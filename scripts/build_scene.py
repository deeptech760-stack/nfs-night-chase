"""Night street race: builds the road, props, skyline, lights, cameras and all animation.

Units: metres. Time step: 1/30 s (one frame). Seed: 7. Staged animation (no physics).
Run it inside blender/nfs_night_chase.blend (Scripting tab > Open > Run Script). It expects the imported assets
that are already in that file: the two cars (CAR_Ferrari, CAR_Concept), the asphalt_02 material, and the
concrete_road_barrier_LOD0 / street_lamp_01 source objects. Safe to re-run: it deletes what it made, then rebuilds.
"""
import math
import random

import bpy
from mathutils import Vector

random.seed(7)
D = bpy.data.objects
scene = bpy.context.scene
FPS, F_END = 30, 360
ROAD_LEN, ROAD_Y = 900.0, 300.0          # road spans y = -150 .. 750
ROAD_W = 13.0
LANE_F, LANE_C = -1.65, 1.65             # Ferrari lane, Concept lane
WHEEL_R = {"Ferrari": 0.36, "Concept": 0.38}
SHOTS = [(1, "chase"), (91, "side"), (172, "flyby"), (250, "front")]
fails = []


def S(obj, attr, val):
    try:
        setattr(obj, attr, val)
    except Exception as e:  # report API differences instead of stopping
        fails.append(f"{type(obj).__name__}.{attr}: {e}")


def link(o):
    scene.collection.objects.link(o)
    return o


# ---------- motion model (plain functions of time) ----------
def y_ferrari(t):
    return 50.0 * t


def gap(t):
    """Concept position relative to the Ferrari: sits 6 m back, creeps up, then nitro from 8.3 s."""
    if t < 3.0:
        return -6.0
    if t < 8.3:
        return -6.0 + (t - 3.0) * (5.0 / 5.3)
    return -1.0 + 0.5 * 3.0 * (t - 8.3) ** 2


def car_state(f):
    t = (f - 1) / FPS
    yf = y_ferrari(t)
    yc = yf + gap(t)
    xf = LANE_F + 0.12 * math.sin(0.9 * t)
    xc = LANE_C + 0.10 * math.sin(0.7 * t + 1.0)
    return t, (xf, yf), (xc, yc)


assert all(car_state(f + 1)[1][1] > car_state(f)[1][1] for f in range(1, F_END)), "Ferrari must always move forward"
assert all(car_state(f + 1)[2][1] > car_state(f)[2][1] for f in range(1, F_END)), "Concept must always move forward"
assert car_state(F_END)[2][1] < ROAD_Y + ROAD_LEN / 2 - 60, "cars must stay on the road"

# ---------- clean up anything from a previous run of this script ----------
for o in list(D):
    if o.name.startswith(("Road", "Sidewalk", "Ground", "Lane", "Bld_", "Lamp_", "LampLight_", "Barrier_", "Cam_", "Tgt_",
                          "Head_", "Tail_", "Glow_", "Nitro")):
        bpy.data.objects.remove(o, do_unlink=True)
for m in list(scene.timeline_markers):
    scene.timeline_markers.remove(m)
for name in ("CAR_Ferrari", "CAR_Concept"):
    D[name].animation_data_clear()
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
scene.frame_start, scene.frame_end = 1, F_END
scene.render.fps = FPS

# ---------- road, sidewalks, ground ----------
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, ROAD_Y, 0))
road = bpy.context.object
road.name = "Road"
road.scale = (ROAD_W + 1.0, ROAD_LEN, 1)
bpy.ops.object.transform_apply(scale=True)
asphalt = bpy.data.materials["asphalt_02"]
road.data.materials.append(asphalt)
nt = asphalt.node_tree
mapping = next(n for n in nt.nodes if n.type == 'MAPPING')
mapping.inputs["Scale"].default_value = ((ROAD_W + 1.0) / 3.0, ROAD_LEN / 3.0, 1.0)
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
if not nt.nodes.get("WetMix"):
    # wet street: rough map darkened, with noise-driven puddles that are almost mirror smooth
    rough_link = bsdf.inputs["Roughness"].links[0]
    src = rough_link.from_socket
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 0.55
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 4.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.48; ramp.color_ramp.elements[1].position = 0.60
    mix = nt.nodes.new("ShaderNodeMix"); mix.name = "WetMix"; mix.data_type = 'FLOAT'
    nt.links.new(src, mul.inputs[0])
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"] if "Fac" in noise.outputs else noise.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs["Color"], mix.inputs[0])
    nt.links.new(mul.outputs[0], mix.inputs[2])
    mix.inputs[3].default_value = 0.04
    nt.links.new(mix.outputs[0], bsdf.inputs["Roughness"])


def flat_mat(name, color, rough, emit=None, strength=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


kerb = flat_mat("Kerb_Concrete", (0.09, 0.09, 0.095), 0.55)
for side, x in (("L", -(ROAD_W / 2 + 3.5)), ("R", ROAD_W / 2 + 3.5)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, ROAD_Y, 0.075))
    s = bpy.context.object
    s.name = f"Sidewalk_{side}"
    s.scale = (6, ROAD_LEN, 0.15)
    bpy.ops.object.transform_apply(scale=True)
    bev = s.modifiers.new("Bevel", 'BEVEL'); bev.width = 0.03; bev.segments = 2
    s.data.materials.append(kerb)
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, ROAD_Y, -0.02))
g = bpy.context.object
g.name = "Ground"
g.scale = (500, ROAD_LEN + 400, 1)
bpy.ops.object.transform_apply(scale=True)
g.data.materials.append(flat_mat("Ground_Dark", (0.012, 0.012, 0.014), 0.7))

# lane markings: dashed lines between lanes, solid edge lines
paint = flat_mat("Lane_Paint", (0.75, 0.75, 0.7), 0.45)
for i, x in enumerate((-3.3, 0.0, 3.3)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, ROAD_Y - ROAD_LEN / 2 + 2, 0.004))
    d = bpy.context.object
    d.name = f"Lane_Dash_{i}"
    d.scale = (0.15, 3.0, 1)
    bpy.ops.object.transform_apply(scale=True)
    arr = d.modifiers.new("Array", 'ARRAY')
    arr.use_relative_offset = False; arr.use_constant_offset = True
    arr.constant_offset_displace = (0, 9.0, 0); arr.count = int(ROAD_LEN / 9.0)
    d.data.materials.append(paint)
for i, x in enumerate((-6.1, 6.1)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, ROAD_Y, 0.004))
    e = bpy.context.object
    e.name = f"Lane_Edge_{i}"
    e.scale = (0.15, ROAD_LEN, 1)
    bpy.ops.object.transform_apply(scale=True)
    e.data.materials.append(paint)

# ---------- Poly Haven props: barriers (array) and street lamps (linked copies with lights) ----------
src_bar = D["concrete_road_barrier_LOD0"]
src_bar.hide_render = True; src_bar.hide_viewport = True
tris = sum(len(p.vertices) - 2 for p in src_bar.data.polygons)
for side, x in (("L", -(ROAD_W / 2 + 0.15)), ("R", ROAD_W / 2 + 0.15)):
    b = link(src_bar.copy())
    b.name = f"Barrier_{side}"
    b.hide_render = False; b.hide_viewport = False
    b.location = (x, ROAD_Y - ROAD_LEN / 2 + 40, 0)
    b.rotation_euler = (0, 0, math.radians(90))
    if tris > 2500:
        dec = b.modifiers.new("Decimate", 'DECIMATE'); dec.ratio = 2500 / tris
    arr = b.modifiers.new("Array", 'ARRAY')
    arr.relative_offset_displace = (1.02, 0, 0)
    arr.count = int((ROAD_LEN - 80) / (src_bar.dimensions.x * 1.02))

src_lamp = D["street_lamp_01"]
src_lamp.hide_render = True; src_lamp.hide_viewport = True
LAMP_SCALE = 1.6
lamp_h = src_lamp.dimensions.z / src_lamp.scale.z * LAMP_SCALE
n = 0
for side, x, y0 in (("L", -(ROAD_W / 2 + 1.2), -60.0), ("R", ROAD_W / 2 + 1.2, -40.0)):
    y = y0
    while y < ROAD_Y + ROAD_LEN / 2 - 20:
        lp = link(src_lamp.copy())
        lp.name = f"Lamp_{side}_{n}"
        lp.hide_render = False; lp.hide_viewport = False
        lp.location = (x, y, 0.15)
        lp.scale = (LAMP_SCALE,) * 3
        lp.rotation_euler = (0, 0, random.uniform(-0.05, 0.05))
        ld = bpy.data.lights.new(f"LampLight_{n}", 'POINT')
        ld.energy = 2500; ld.color = (1.0, 0.60, 0.26); ld.shadow_soft_size = 0.25
        ld.use_shadow = False                    # 40 lamps: unshadowed keeps the frame time down
        lo = link(bpy.data.objects.new(f"LampLight_{n}", ld))
        lo.location = (x * 0.93, y, 0.15 + lamp_h * 0.86)
        n += 1
        y += 40.0

# ---------- skyline: no CC0 building assets fit, so blocks with a procedural lit-window material ----------
win = bpy.data.materials.get("Bld_Windows") or bpy.data.materials.new("Bld_Windows")
win.use_nodes = True
wt = win.node_tree
wt.nodes.clear()
out = wt.nodes.new("ShaderNodeOutputMaterial")
pb = wt.nodes.new("ShaderNodeBsdfPrincipled")
pb.inputs["Base Color"].default_value = (0.02, 0.022, 0.028, 1); pb.inputs["Roughness"].default_value = 0.35
tc = wt.nodes.new("ShaderNodeTexCoord")
sep = wt.nodes.new("ShaderNodeSeparateXYZ"); comb = wt.nodes.new("ShaderNodeCombineXYZ")
brick = wt.nodes.new("ShaderNodeTexBrick")
brick.inputs["Color1"].default_value = (0, 0, 0, 1); brick.inputs["Color2"].default_value = (1, 1, 1, 1)
brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
brick.inputs["Scale"].default_value = 1.0
brick.inputs["Mortar Size"].default_value = 0.55
brick.inputs["Brick Width"].default_value = 2.0; brick.inputs["Row Height"].default_value = 3.2
brick.offset = 0.0
ramp = wt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = 'CONSTANT'
ramp.color_ramp.elements[1].position = 0.72
tint = wt.nodes.new("ShaderNodeValToRGB")
tint.color_ramp.elements[0].position = 0.72; tint.color_ramp.elements[0].color = (1.0, 0.55, 0.2, 1)
tint.color_ramp.elements[1].position = 1.0; tint.color_ramp.elements[1].color = (0.45, 0.75, 1.0, 1)
inv = wt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
mulw = wt.nodes.new("ShaderNodeMath"); mulw.operation = 'MULTIPLY'
strength = wt.nodes.new("ShaderNodeMath"); strength.operation = 'MULTIPLY'; strength.inputs[1].default_value = 1.6
wt.links.new(tc.outputs["Object"], sep.inputs[0])
wt.links.new(sep.outputs["Y"], comb.inputs["X"]); wt.links.new(sep.outputs["Z"], comb.inputs["Y"])
wt.links.new(comb.outputs[0], brick.inputs["Vector"])
wt.links.new(brick.outputs["Color"], ramp.inputs[0]); wt.links.new(brick.outputs["Color"], tint.inputs[0])
wt.links.new(brick.outputs["Fac"], inv.inputs[1])
wt.links.new(ramp.outputs["Color"], mulw.inputs[0]); wt.links.new(inv.outputs[0], mulw.inputs[1])
wt.links.new(mulw.outputs[0], strength.inputs[0])
wt.links.new(tint.outputs["Color"], pb.inputs["Emission Color"])
wt.links.new(strength.outputs[0], pb.inputs["Emission Strength"])
wt.links.new(pb.outputs[0], out.inputs["Surface"])
k = 0
for sx in (-1, 1):
    y = ROAD_Y - ROAD_LEN / 2
    while y < ROAD_Y + ROAD_LEN / 2:
        w = random.uniform(18, 34); h = random.uniform(14, 48); dep = random.uniform(14, 22)
        setback = random.uniform(0.0, 5.0)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx * (ROAD_W / 2 + 7.5 + setback + dep / 2), y + w / 2, h / 2))
        b = bpy.context.object
        b.name = f"Bld_{k}"; k += 1
        b.scale = (dep, w, h)
        bpy.ops.object.transform_apply(scale=True)
        b.data.materials.append(win)
        y += w + random.uniform(1.5, 6.0)

# ---------- cars: orient, recolour the concept car, lights ----------
ferrari, concept = D["CAR_Ferrari"], D["CAR_Concept"]
ferrari.rotation_euler = (0, 0, 0)
concept.rotation_euler = (0, 0, math.pi)      # its model faces -Y; the race runs towards +Y


def principled(mat_name):
    m = bpy.data.materials.get(mat_name)
    return next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if m else None


def emit(mat_name, color, strength):
    b = principled(mat_name)
    if not b:
        fails.append(f"no material {mat_name}")
        return
    for l in list(b.inputs["Emission Color"].links):
        b.id_data.links.remove(l)
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = strength


for name in ("Paint 1 Carmine", "Paint 2 Carmine"):
    b = principled(name)
    if b:
        linked = bool(b.inputs["Base Color"].links)
        for l in list(b.inputs["Base Color"].links):
            b.id_data.links.remove(l)
        b.inputs["Base Color"].default_value = (0.005, 0.05, 0.55, 1) if name.startswith("Paint 1") else (0.01, 0.01, 0.012, 1)
        b.inputs["Metallic"].default_value = 0.6
        b.inputs["Roughness"].default_value = 0.25
        print("repaint", name, "had texture" if linked else "plain")
emit("Brakelight", (1.0, 0.02, 0.01), 25.0)
emit("Headlight", (0.85, 0.92, 1.0), 40.0)
# the Ferrari's lamp meshes share materials with other parts: give each its own emissive copy
for obj_name, col, st in (("lights", (0.85, 0.92, 1.0), 5.0), ("leds", (0.9, 0.95, 1.0), 25.0), ("lights_red", (1.0, 0.02, 0.01), 25.0)):
    o = D[obj_name]
    for slot in o.material_slots:
        if not slot.material.name.startswith("Emit_"):
            slot.material = slot.material.copy()
            slot.material.name = f"Emit_{obj_name}"
        emit(slot.material.name, col, st)

GLOW = {"Ferrari": (1.0, 0.05, 0.55), "Concept": (0.0, 0.85, 1.0)}
for name, root in (("Ferrari", ferrari), ("Concept", concept)):
    fwd = 1.0 if name == "Ferrari" else -1.0      # local +Y or -Y is the nose
    for sx in (-0.62, 0.62):
        hd = bpy.data.lights.new(f"Head_{name}", 'SPOT')
        hd.energy = 2200; hd.spot_size = math.radians(70); hd.spot_blend = 0.6; hd.color = (0.85, 0.92, 1.0)
        hd.shadow_soft_size = 0.05
        ho = link(bpy.data.objects.new(f"Head_{name}_{'L' if sx < 0 else 'R'}", hd))
        ho.parent = root
        ho.location = (sx, fwd * 2.05, 0.62)
        # spot looks down its -Z: tip it to face the nose, 4 degrees below the horizon
        ho.rotation_euler = (math.radians(86), 0, 0 if fwd > 0 else math.pi)
        tl = bpy.data.lights.new(f"Tail_{name}", 'POINT')
        tl.energy = 60; tl.color = (1.0, 0.03, 0.02); tl.shadow_soft_size = 0.1
        to = link(bpy.data.objects.new(f"Tail_{name}_{'L' if sx < 0 else 'R'}", tl))
        to.parent = root
        to.location = (sx, -fwd * 2.45, 0.75)
    gl = bpy.data.lights.new(f"Glow_{name}", 'AREA')
    gl.shape = 'RECTANGLE'; gl.size = 1.5; gl.size_y = 3.6; gl.energy = 700; gl.color = GLOW[name]
    go = link(bpy.data.objects.new(f"Glow_{name}", gl))
    go.parent = root
    go.location = (0, 0, 0.05)

nd = bpy.data.lights.new("Nitro", 'POINT')
nd.color = (0.2, 0.5, 1.0); nd.energy = 0; nd.shadow_soft_size = 0.15
nitro = link(bpy.data.objects.new("Nitro", nd))
nitro.parent = concept
nitro.location = (0, 2.6, 0.35)               # behind the concept car (its local +Y is the tail)

# ---------- wheels: spin about the axle, angle = distance / radius ----------
WHEELS = {"Ferrari": ["wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"],
          "Concept": ["WheelFrontL", "WheelFrontR", "WheelRearL", "WheelRearR"]}
bpy.context.view_layer.update()
wheel_axes = {}
for car, names in WHEELS.items():
    for wn in names:
        w = D[wn]
        w.animation_data_clear()
        q = w.matrix_basis.to_quaternion()
        local = w.matrix_world.to_3x3().inverted() @ Vector((1, 0, 0))
        idx = max(range(3), key=lambda i: abs(local[i]))
        sign = 1.0 if local[idx] > 0 else -1.0
        mode = ("XYZ", "YXZ", "ZXY")[idx]
        w.rotation_mode = mode
        w.rotation_euler = q.to_euler(mode)
        wheel_axes[wn] = (idx, sign, w.rotation_euler[idx], car)

# ---------- cameras: one per shot, switched by timeline markers ----------
cams = {}
for start, shot in SHOTS:
    cd = bpy.data.cameras.new(f"Cam_{shot}")
    cd.lens = {"chase": 22, "side": 20, "flyby": 20, "front": 40}[shot]
    cd.clip_end = 2000
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 4.0
    co = link(bpy.data.objects.new(f"Cam_{shot}", cd))
    tgt = link(bpy.data.objects.new(f"Tgt_{shot}", None))
    tgt.empty_display_size = 0.3
    con = co.constraints.new('TRACK_TO')
    con.target = tgt; con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
    cd.dof.focus_object = tgt
    cams[shot] = (co, tgt)
    mk = scene.timeline_markers.new(shot, frame=start)
    mk.camera = co
scene.camera = cams["chase"][0]


def shot_of(f):
    cur = SHOTS[0]
    for s in SHOTS:
        if f >= s[0]:
            cur = s
    nxt = next((s[0] for s in SHOTS if s[0] > cur[0]), F_END + 1)
    return cur[1], (f - cur[0]) / max(1, nxt - 1 - cur[0])


flyby_y = car_state(222)[1][1]            # the cars reach the camera near the end of the shot


def camera_pose(shot, s, state):
    _, (xf, yf), (xc, yc) = state
    if shot == "chase":      # low, behind the Ferrari, creeping closer
        return (xf - 1.3, yf - 7.0 + 1.5 * s, 0.50 + 0.25 * s), (xf + 0.9, yf + 2.0, 0.65)
    if shot == "side":       # tracking alongside at wheel height
        return (-5.9, yf + 1.5 - 4.0 * s, 0.65), (0.0, yf - 1.5, 0.55)
    if shot == "flyby":      # locked off at the kerb, pans with the cars
        return (-5.6, flyby_y, 0.35), ((xf + xc) / 2, (yf + yc) / 2, 0.6)
    lead = max(yf, yc)       # front: ahead of the leader, craning up
    return (0.4 * math.sin(3 * s), lead + 9.0 + 3.0 * s, 0.55 + 1.9 * s), ((xf + xc) / 2, (yf + yc) / 2 + 1.0, 0.6)


# ---------- keyframes ----------
y_start = {"Ferrari": car_state(1)[1][1], "Concept": car_state(1)[2][1]}
for f in range(1, F_END + 1):
    st = car_state(f)
    t, (xf, yf), (xc, yc) = st
    ferrari.location = (xf, yf, 0); ferrari.keyframe_insert("location", frame=f)
    concept.location = (xc, yc, 0); concept.keyframe_insert("location", frame=f)
    for wn, (idx, sign, base, car) in wheel_axes.items():
        dist = (yf if car == "Ferrari" else yc) - y_start[car]
        w = D[wn]
        # rolling towards +Y is a negative turn about world +X; sign maps that onto the wheel's own axle axis
        w.rotation_euler[idx] = base - sign * dist / WHEEL_R[car]
        w.keyframe_insert("rotation_euler", index=idx, frame=f)
    nd.energy = 0.0 if t < 8.3 else min(1.0, (t - 8.3) / 0.25) * (1500 + 500 * math.sin(40 * t))
    nd.keyframe_insert("energy", frame=f)
    shot, s = shot_of(f)
    co, tgt = cams[shot]
    pos, look = camera_pose(shot, s, st)
    shake = 0.0 if shot == "flyby" else 0.012
    co.location = tuple(p + random.uniform(-shake, shake) for p in pos)
    co.keyframe_insert("location", frame=f)
    tgt.location = look
    tgt.keyframe_insert("location", frame=f)

# ---------- render settings ----------
r = scene.render
for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        r.engine = eng
        break
    except Exception:
        pass
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
S(r, "use_motion_blur", True)
S(r, "motion_blur_shutter", 0.4)
ee = scene.eevee
S(ee, "taa_render_samples", 16)
S(ee, "motion_blur_steps", 4)
S(ee, "use_raytracing", True)
S(ee, "use_shadows", True)
try:
    ee.ray_tracing_options.resolution_scale = '2'
    ee.ray_tracing_options.screen_trace_quality = 0.5
except Exception as e:
    fails.append(f"ray_tracing_options: {e}")
S(scene.view_settings, "view_transform", "AgX")
S(scene.view_settings, "look", "AgX - Punchy")
bg = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
bg.inputs["Strength"].default_value = 0.6

# bloom on lamps, headlights and neon (compositor glare)
try:
    tree = bpy.data.node_groups.get("NFS_Comp") or bpy.data.node_groups.new("NFS_Comp", "CompositorNodeTree")
    tree.nodes.clear()
    if not tree.interface.items_tree:
        tree.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    gout = tree.nodes.new("NodeGroupOutput")
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], gout.inputs[0])
    for key, val in (("Type", "Bloom"), ("Threshold", 2.0), ("Strength", 0.5), ("Size", 0.6)):
        try:
            glare.inputs[key].default_value = val
        except Exception as e:
            fails.append(f"glare {key}: {e} / inputs {[i.name for i in glare.inputs]}")
    scene.compositing_node_group = tree
    S(r, "use_compositing", True)
except Exception as e:
    fails.append(f"compositor: {e}")

r.image_settings.file_format = 'PNG'
r.filepath = "//renders/frames/f_"
scene.frame_set(1)
bpy.ops.wm.save_mainfile()
print("ENGINE", r.engine, "barrier tris", tris, "lamps", n, "buildings", k)
print("WHEEL AXES", {k2: (v[0], v[1]) for k2, v in wheel_axes.items()})
print("FAILS", fails)
