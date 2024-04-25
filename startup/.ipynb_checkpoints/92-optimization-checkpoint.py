import pandas as pd
import scipy as sp

from ophyd import Device, EpicsSignal
from ophyd import Component as Cpt

import bluesky.plan_stubs as bps
import bluesky.plans as bp
import numpy as np



from blop import DOF, Objective, Agent
from blop.utils.misc import best_image_feedback


def list_scan_with_delay(*args, delay=0, bimorph=bimorph, **kwargs):
    "Accepts all the normal 'scan' parameters, plus an optional delay."

    def armed_residuals(bimorph):
        return (bimorph.all_armed_voltages() - bimorph.all_setpoint_voltages())[12:24]
        
    def ramp_residuals(bimorph):
        return (bimorph.all_current_voltages.get() - bimorph.all_setpoint_voltages())[12:24]

    def one_nd_step_with_delay(detectors, step, pos_cache):
        "This is a copy of bluesky.plan_stubs.one_nd_step with a sleep added."

        motors = step.keys()

        yield from bps.move_per_step(step, pos_cache)

        

        timeout_ms = 10e3
        tolerance_volts = 1e0
        check_every_ms = 5e2

        start_time = ttime.monotonic()
        while not all(np.abs(armed_residuals(bimorph)) < tolerance_volts):
            
            print("waiting for voltages to arm...")
            print(f"residuals: {armed_residuals(bimorph)}")
            time.sleep(1e-3*check_every_ms)

            if 1e3 * (ttime.monotonic() - start_time) > timeout_ms:
                raise TimeoutError()
        
        yield from bimorph.start_plan()

        start_time = ttime.monotonic()
        while not all(np.abs(ramp_residuals(bimorph)) < tolerance_volts):

            print("ramping...")
            print(f"residuals: {ramp_residuals(bimorph)}")
            time.sleep(1e-3*check_every_ms)

            if 1e3 * (ttime.monotonic() - start_time) > timeout_ms:
                raise TimeoutError()

        # bimorph_setpoints = np.array([getattr(bimorph, f"channels.channel{i}.setpoint").get() for i in range(32)])
        # residual = (bimorph.all_current_voltages.get() - bimorph_setpoints)[12:24]

        # while not all(np.abs(residual) < tolerance_volts):

        #     bimorph_setpoints = np.array([getattr(bimorph, f"channels.channel{i}.setpoint").get() for i in range(32)])
        #     residual = (bimorph.all_current_voltages.get() - bimorph_setpoints)[12:24]
        #     print(residual.round(1))

        #     if 1e3 * (ttime.monotonic() - start_time) > timeout_ms:
        #         raise TimeoutError()

        #     time.sleep(1e-3 * check_every_ms)

        #yield from bps.sleep(delay)
        yield from bps.trigger_and_read(list(detectors) + list(motors))


    kwargs.setdefault("per_step", one_nd_step_with_delay)
    uid = yield from bp.list_scan(*args, **kwargs)
    return uid


# def list_scan_with_delay(*args, delay=0, device=bimorph, **kwargs):
#     "Accepts all the normal 'scan' parameters, plus an optional delay."

    

#     def one_nd_step_with_delay(detectors, step, pos_cache):
#         "This is a copy of bluesky.plan_stubs.one_nd_step with a sleep added."

#         print("starting step")
        
#         motors = step.keys()
#         yield from bps.move_per_step(step, pos_cache)

#         print("waiting")
        
        


#     kwargs.setdefault("per_step", one_nd_step_with_delay)
#     uid = yield from bp.list_scan(*args, **kwargs)
#     return uid

def bimorph_acquisition_plan(dofs, inputs, dets, **kwargs):
    delay = kwargs.get("delay", 0)
    args = []
    for dof, points in zip(dofs, np.atleast_2d(inputs).T):
        args.append(dof)
        args.append(list(points))

    uid = yield from list_scan_with_delay(dets, *args, delay=delay)
    return uid





#def best_image_feedback():

    


def digestion(db, uid):

    products = db[uid].table(fill=True)

    products["cropped_image"] = pd.Series(dtype="object")

    products["processed_image"] = pd.Series(dtype="object")


    cropped_images = []

    processed_images = []

    for index, entry in products.iterrows():

        print(index)

        x_min = entry.camSS_roi1_min_xyz_min_x
        y_min = entry.camSS_roi1_min_xyz_min_y

        x_max = x_min + entry.camSS_roi1_size_x
        y_max = y_min + entry.camSS_roi1_size_y

        image = entry.camSS_image[0]

        cim = image[y_min:y_max, x_min:x_max].astype(float).sum(axis=-1)

        cropped_images.append(cim)

        n_y, n_x = cim.shape

        fcim = sp.ndimage.median_filter(cim, size=1)
        fcim = fcim - np.median(fcim, axis=1)[:, None]

        THRESHOLD = 0.05 * fcim.max()

        mfcim = np.where(fcim > THRESHOLD, fcim, 0)

        x_weight = mfcim.sum(axis=0)
        y_weight = mfcim.sum(axis=1)

        time = ttime.time()

        #$plt.plot(x_weight)
        plt.figure()
        plt.imshow(cim)
        plt.savefig(f"{int(time)}.png")
        #plt.plot(y_weight)

        x = np.arange(n_x)
        y = np.arange(n_y)

        x0 = np.sum(x_weight * x) / np.sum(x_weight)
        y0 = np.sum(y_weight * y) / np.sum(y_weight)

        xw = 2 * np.sqrt((np.sum(x_weight * x**2) / np.sum(x_weight) - x0**2))
        yw = 2 * np.sqrt((np.sum(y_weight * y**2) / np.sum(y_weight) - y0**2))

        area_pixels = (mfcim > THRESHOLD).sum()

        processed_images.append(mfcim)

        products.loc[index, "area"] = area_pixels

        # bad = False
        # bad |= x0 < 16
        # bad |= x0 > nx - 16
        # bad |= y0 < 16
        # bad |= y0 > ny - 16

        # if bad:
        #     x0, xw, y0, yw = 4 * [np.nan]

        products.loc[index, "pos_x"] = x0
        products.loc[index, "pos_y"] = y0
        products.loc[index, "wid_x"] = xw 
        products.loc[index, "wid_y"] = yw

    #products.loc[:, "cropped_image"] = cropped_images
    #products.loc[:, "processed_image"] = processed_images

    return products


fid_voltages = bimorph.all_target_voltages.get()   


# first 12 are horizontal
# second 12 are vertical
# last 8?????

fid_voltages = [-253. , -261. , -260. , -260. , -266.8, -260. , -469.3, -260. ,
                -260. , -590.7, -260. , -510.7, -321. , -371. , -270. , -270. ,
                -195. , -195. , -195. , -195. , -195. , -195. , -195. , -195. ,
                    0. ,    0. ,    0. ,    0. ,    0. ,    0. ,    0. ,    0. ]


dofs = []

voltage_radius = 400

for i in range(12):


    device = getattr(pseudo_bimorph, f"r{i}")
    device.readback.name = device.name

    center = device.read()[device.name]["value"]

    dof = DOF(device=device, 
              description=f"piezo {i}", 
              search_bounds=(-350, 100),
              units="V",
              )


    # device = getattr(pseudo_bimorph, f"p{i}")
    # #device.readback.name = device.name

    # center = device.read()[device.name]["value"]

    # dof = DOF(device=device, 
    #           description=("constant" if i == 0 else f"diff {i-1}->{i}"), 
    #           search_bounds=(center-100, center+100),
    #           units="V",
    #           )


    dofs.append(dof)

objectives = [
    Objective(name="area", description="beam area", log=True, target="min")
]

#scn_SS = setup_cam('camSS')

scnSS.cam.ext_trig = True

dets = [scnSS.cam]

agent = Agent(dofs=dofs, 
                objectives=objectives, 
                dets=dets, 
                digestion=digestion, 
                acquistion_plan=bimorph_acquisition_plan, 
                db=db,
                verbose=True,
                trigger_delay=0.1)

# agent.dofs.deactivate()

# for dof in agent.dofs[2:]:
#     dof.active = False

# agent.dofs[0].search_bounds = (-500, -100)
# agent.dofs[1].search_bounds = (-200, 200)
# agent.dofs[2].search_bounds = (-200, 200)
# agent.dofs[3].search_bounds = (-200, 200)

def plot_all_profiles(agent, axis=0):

    images = np.array(agent.table.cropped_image.values)

    for im in images:

        plt.plot(im.sum(axis=axis))

def plot_all_images(agent):

    images = np.array(agent.table.cropped_image.values)

    nx = int(np.sqrt(len(images)))
    ny = len(images) // nx + 1

    fig, axes = plt.subplots(nx, ny, figsize=(nx, ny))

    axes = np.atleast_2d(axes)

    for iax in range(len(images)):

        im = images[iax]
        ax = axes.ravel()[iax]

        ax.imshow(im)


from ophyd.pseudopos import (
    PseudoPositioner,
    PseudoSingle,
    pseudo_position_argument,
    real_position_argument
)
from ophyd import Component, SoftPositioner

import numpy as np
import scipy as sp

