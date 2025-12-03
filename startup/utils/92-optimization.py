import copy
import functools
import time as ttime
from typing import Any
import pandas as pd
import scipy as sp
import cv2

from ophyd import Device, EpicsSignal
from ophyd import Component as Cpt

from bluesky.utils import MsgGenerator
import bluesky.plan_stubs as bps
import bluesky.plans as bp
import numpy as np



from blop import DOF, Objective, Agent
from blop.ax import Agent as AxAgent
from blop.plans import default_acquire
from blop.dofs import DOFConstraint
from blop.protocols import OptimizationProblem


# def list_scan_with_delay(*args, delay=0, bimorph=bimorph, **kwargs):
#     "Accepts all the normal 'scan' parameters, plus an optional delay."
# 
#     def arm_residuals(bimorph):
#         return (bimorph.all_armed_voltages() - bimorph.all_setpoint_voltages())[12:24]
#         
#     def ramp_residuals(bimorph):
#         return (bimorph.all_current_voltages.get() - bimorph.all_setpoint_voltages())[12:24]
# 
#     def one_nd_step_with_delay(detectors, step, pos_cache):
#         "This is a copy of bluesky.plan_stubs.one_nd_step with a sleep added."
# 
#         motors = step.keys()
# 
#         yield from bps.move_per_step(step, pos_cache)
# 
#         timeout_ms = 10e3
#         tolerance_volts = 1e0
#         check_every_ms = 1e3
# 
#         start_time = ttime.monotonic()
#         while not all(np.abs(arm_residuals(bimorph)) < tolerance_volts):
#             
#             print(f"arming... (residuals = {np.array2string(arm_residuals(bimorph), precision=0, floatmode='fixed')} V)")
#             time.sleep(1e-3*check_every_ms)
# 
#             if 1e3 * (ttime.monotonic() - start_time) > timeout_ms:
#                 raise TimeoutError()
# 
#         yield from bimorph.start_plan()
# 
#         start_time = ttime.monotonic()
#         while not all(np.abs(ramp_residuals(bimorph)) < tolerance_volts):
# 
#             print(f"ramping... (residuals = {np.array2string(ramp_residuals(bimorph), precision=0, floatmode='fixed')} V)")
#             time.sleep(1e-3*check_every_ms)
# 
#             if 1e3 * (ttime.monotonic() - start_time) > timeout_ms:
#                 raise TimeoutError()
# 
#         yield from bps.sleep(1.0)
#         yield from bps.trigger_and_read(list(detectors) + list(motors))
# 
# 
#     kwargs.setdefault("per_step", one_nd_step_with_delay)
#     uid = yield from bp.list_scan(*args, **kwargs)
#     return uid
# 
# 
# #     kwargs.setdefault("per_step", one_nd_step_with_delay)
# #     uid = yield from bp.list_scan(*args, **kwargs)
# #     return uid
# 
# def bimorph_acquisition_plan(dofs, inputs, dets, **kwargs):
#     delay = kwargs.get("delay", 0)
#     args = []
#     for dof, points in zip(dofs, np.atleast_2d(inputs).T):
#         args.append(dof)
#         args.append(list(points))
# 
#     yield from bps.mv(scnSS.y, 0)
#     yield from bps.sleep(1.0)
# 
#     uid = yield from list_scan_with_delay(dets, *args, delay=delay)
# 
#     yield from bps.mv(scnSS.y, 3)
# 
#     return uid
# 
# 
# def digestion(db, uid):
# 
#     products = db[uid].table(fill=True)
# 
#     products["cropped_image"] = pd.Series(dtype="object")
# 
#     products["processed_image"] = pd.Series(dtype="object")
# 
#     products["beam_profile_y"] = pd.Series(dtype="object")
# 
# 
#     cropped_images = []
# 
#     processed_images = []
# 
#     for index, entry in products.iterrows():
# 
#         print(index)
# 
#         x_min = entry.camSS_roi1_min_xyz_min_x
#         y_min = entry.camSS_roi1_min_xyz_min_y
# 
#         x_max = x_min + entry.camSS_roi1_size_x
#         y_max = y_min + entry.camSS_roi1_size_y
# 
#         image = entry.camSS_image[0]
# 
#         cim = image[y_min:y_max, x_min:x_max].astype(float).sum(axis=-1)
# 
#         cropped_images.append(cim)
# 
#         n_y, n_x = cim.shape
# 
#         fcim = sp.ndimage.median_filter(cim, size=1)
#         fcim = fcim - np.median(fcim, axis=1)[:, None]
# 
#         THRESHOLD = 0.1 * fcim.max()
# 
#         mfcim = np.where(fcim > THRESHOLD, fcim, 0)
# 
#         x_weight = mfcim.sum(axis=0)
#         y_weight = mfcim.sum(axis=1)
# 
#         time = ttime.time()
# 
#         #$plt.plot(x_weight)
#         # plt.figure()
#         # plt.imshow(cim, aspect="auto")
#         # plt.savefig(f"{int(time)}.png")
#         #plt.plot(y_weight)
# 
#         x = np.arange(n_x)
#         y = np.arange(n_y)
# 
#         x0 = np.sum(x_weight * x) / np.sum(x_weight)
#         y0 = np.sum(y_weight * y) / np.sum(y_weight)
# 
#         xw = 2 * np.sqrt((np.sum(x_weight * x**2) / np.sum(x_weight) - x0**2))
#         yw = 2 * np.sqrt((np.sum(y_weight * y**2) / np.sum(y_weight) - y0**2))
# 
#         area_pixels = (mfcim > THRESHOLD).sum()
# 
#         processed_images.append(mfcim)
# 
#         products.loc[index, "area"] = area_pixels
# 
#         products.at[index, "beam_profile_y"] = y_weight
# 
#         # bad = False
#         # bad |= x0 < 16
#         # bad |= x0 > nx - 16
#         # bad |= y0 < 16
#         # bad |= y0 > ny - 16
# 
#         # if bad:
#         #     x0, xw, y0, yw = 4 * [np.nan]
# 
#         products.loc[index, "pos_x"] = x0
#         products.loc[index, "pos_y"] = y0
#         products.loc[index, "wid_x"] = xw 
#         products.loc[index, "wid_y"] = yw
# 
#     products.loc[:, "cropped_image"] = cropped_images
#     products.loc[:, "processed_image"] = processed_images
# 
#     return products
# 
# 
# fid_voltages = bimorph.all_target_voltages.get()   
# 
# 
# # first 12 are horizontal
# # second 12 are vertical
# # last 8?????
# 
# fid_voltages = [-253. , -261. , -260. , -260. , -266.8, -260. , -469.3, -260. ,
#                 -260. , -590.7, -260. , -510.7, -321. , -371. , -270. , -270. ,
#                 -195. , -195. , -195. , -195. , -195. , -195. , -195. , -195. ,
#                     0. ,    0. ,    0. ,    0. ,    0. ,    0. ,    0. ,    0. ]
# 
# 
# dofs = []
# 
# voltage_radius = 400
# 
# for i in range(12):
# 
# 
#     device = getattr(pseudo_bimorph, f"r{i}")
#     device.readback.name = device.name
# 
#     center = device.read()[device.name]["value"]
# 
#     dof = DOF(device=device, 
#               description=f"piezo {i}", 
#               search_bounds=(center-100, center+100),
#               units="V",
#               )
# 
# 
#     device = getattr(pseudo_bimorph, f"p{i}")
#     #device.readback.name = device.name
# 
#     center = 0 #device.read()[device.name]["value"]
# 
#     pseudo_radius = 500. / (2. ** i)
# 
#     dof = DOF(device=device, 
#               description=(f"pseudo {i}"), 
#               search_bounds=(center-pseudo_radius, center+pseudo_radius),
#               units="V",
#               )
# 
# 
#     dofs.append(dof)
# 
# objectives = [
#     Objective(name="wid_y", description="beam height", log=True, target="min")
# ]
# 
# #scnSS = setup_cam('camSS')
# 
# scnSS.cam.ext_trig = False
# 
# dets = [scnSS.cam]
# 
# agent = Agent(dofs=dofs, 
#                 objectives=objectives, 
#                 dets=dets, 
#                 digestion=digestion, 
#                 acquistion_plan=bimorph_acquisition_plan, 
#                 db=db,
#                 verbose=True,
#                 trigger_delay=0.1)
# 
# # agent.dofs.deactivate()
# 
# for dof in agent.dofs[6:]:
#     dof.active = False
# 
# agent.dofs[0].search_bounds = (-100, 100)
# agent.dofs[1].search_bounds = (-100, 100)
# agent.dofs[2].search_bounds = (-100, 100)
# agent.dofs[3].search_bounds = (-100, 100)
# agent.dofs[4].search_bounds = (-100, 100)
# agent.dofs[5].search_bounds = (-100, 100)
# 
# def plot_all_profiles(agent, axis=0):
# 
#     images = np.array(agent.table.cropped_image.values)
# 
#     for im in images:
# 
#         plt.plot(im.sum(axis=axis))
# 
# def plot_all_images(agent):
# 
#     images = np.array(agent.table.cropped_image.values)
# 
#     nx = int(np.sqrt(len(images)))
#     ny = len(images) // nx + 1
# 
#     fig, axes = plt.subplots(nx, ny, figsize=(nx, ny))
# 
#     axes = np.atleast_2d(axes)
# 
#     for iax in range(len(images)):
# 
#         im = images[iax]
#         ax = axes.ravel()[iax]
# 
#         ax.imshow(im)


from ophyd.pseudopos import (
    PseudoPositioner,
    PseudoSingle,
    pseudo_position_argument,
    real_position_argument
)
from ophyd import Component, SoftPositioner

import numpy as np
import scipy as sp


def vertical_profile_metric(image, background=None, threshold_factor=0.1,
                           intensity_weight=1.0, uniformity_weight=1.0,
                           edge_crop=0):
    """
    Metric for vertical beam uniformity optimization (for vertical focusing mirror).
    Collapses image to 1D vertical profile and optimizes for uniformity + intensity.
    
    Lower values = better (minimize this metric).
    
    :param image: OpenCV image (BGR or grayscale)
    :param background: Optional background image for subtraction
    :param threshold_factor: Fraction of max intensity for beam detection (default 0.1)
    :param intensity_weight: Weight for intensity maximization term
    :param uniformity_weight: Weight for vertical uniformity term
    :param edge_crop: Number of pixels to crop from the edges of the image. Default to 0.
    :return: Tuple (metric: float, debug_image: OpenCV image, metrics_dict: dict)
    """
    # Convert to grayscale
    image = image.squeeze()
    if len(image.shape) == 3 and image.shape[0] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Crop edges to remove artifacts
    if edge_crop > 0:
        gray = gray[edge_crop:-edge_crop, edge_crop:-edge_crop]
        if background is not None:
            background = background[edge_crop:-edge_crop, edge_crop:-edge_crop]
    
    # Background subtraction
    if background is None:
        background = np.zeros_like(gray)
    else:
        if len(background.shape) == 3:
            background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    corrected = cv2.subtract(gray, background)
    corrected = cv2.GaussianBlur(corrected, (5, 5), 0)
    max_intensity = np.max(corrected)
    if max_intensity == 0:
        return float('inf'), None, {}
        
    thresh_value = threshold_factor * max_intensity
    _, thresh = cv2.threshold(corrected, thresh_value, 255, cv2.THRESH_TOZERO)
    
    # ========== VERTICAL PROFILE ==========
    # Collapse to 1D vertical profile by summing over horizontal (x) axis
    vertical_profile = np.sum(thresh, axis=1)
    
    if len(vertical_profile) == 0 or np.sum(vertical_profile) == 0:
        return float('inf'), None, {}
    
    # ========== UNIFORMITY METRIC ==========
    # Coefficient of variation (CV) = std / mean
    mean_intensity = np.mean(vertical_profile)
    std_intensity = np.std(vertical_profile)
    cv = std_intensity / mean_intensity if mean_intensity > 0 else float('inf')
    
    # ========== TOTAL INTENSITY ==========
    # Total integrated intensity (sum of profile)
    total_intensity = np.sum(vertical_profile)
    
    # ========== DEBUG VISUALIZATION ==========
    # Plot vertical profile to the right of the image
    #profile_width = 150
    #profile_x_start = debug_img.shape[1] - profile_width - 10
    
    # Normalize profile for plotting
    #if np.max(vertical_profile) > 0:
    #    normalized_profile = (vertical_profile / np.max(vertical_profile)) * profile_width
    #else:
    #    normalized_profile = np.zeros_like(vertical_profile)
    
    # Draw profile graph (rotated - grows to the right)
    # Profile spans full image height (0 to image height)
    # for i in range(len(normalized_profile) - 1):
    #     pt1 = (profile_x_start + int(normalized_profile[i]), i)
    #     pt2 = (profile_x_start + int(normalized_profile[i + 1]), i + 1)
    #     cv2.line(debug_img, pt1, pt2, (255, 255, 0), 2)
    
    # Draw baseline for profile (full height)
    # cv2.line(debug_img, (profile_x_start, 0), (profile_x_start, debug_img.shape[0]), (255, 255, 255), 1)
    
    # Text overlays
    # text_x = 10
    # cv2.putText(debug_img, f"CV (Uniformity): {cv:.4f}", 
    #             (text_x, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    # cv2.putText(debug_img, f"Total Intensity: {total_intensity:.1f}", 
    #             (text_x, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    # cv2.putText(debug_img, f"Mean: {mean_intensity:.1f}", 
    #             (text_x, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    # cv2.putText(debug_img, f"Std Dev: {std_intensity:.1f}", 
    #             (text_x, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    # cv2.putText(debug_img, f"Metric: {metric:.4f}", 
    #             (text_x, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    
    metrics_dict = {
        'cv': cv,
        'total_intensity': total_intensity,
        'mean_intensity': mean_intensity,
        'std_intensity': std_intensity,
        'vertical_profile': vertical_profile
    }
    
    return 0.0, None, metrics_dict

optimization_detectors = [
    #scnSS,
    # scnSF.cam,
    ktx22,
    ext_trig,
    pil,
]

def vertical_profile_digestion(
    uid: str,
    suggestions: list[dict],
    threshold_factor: float = 0.1,
    edge_crop: int = 0,
) -> dict[str, float | tuple[float, float]]:
    """
    Digestion function for vertical profile optimization.

    Parameters
    ----------
    trial_index : int
        The index of the trial.
    readings : dict[str, list[Any]]
        The readings from the optimization detectors.
    threshold_factor : float, optional
        The factor to multiply the maximum intensity by to get the threshold for the vertical profile. Default to 0.1.
    edge_crop : int, optional
        The number of pixels to crop from the edges of the image. Default to 0.
    """
    suggestion = suggestions[0]
    image = np.array(list(db[uid].data(f"{optimization_detectors[0].name}_image"))[0])
    _, _, metrics_dict = vertical_profile_metric(image, threshold_factor=threshold_factor, edge_crop=edge_crop)
    return [{
        "vertical_coefficient_variation": metrics_dict["cv"],
        "total_vertical_intensity": metrics_dict["total_intensity"],
        "_id": suggestion["_id"]
    }]


def _get_channel_neighbors(channel: int) -> list[Channel]:
    """Helper function to get the neighbors of a channel in the bimorph."""
    neighbors_indices = []
    # Horizontal mirror channels: 0-11
    if 0 <= channel <= 11:
        if channel == 0:
            neighbors_indices.append(1)
        elif channel == 11:
            neighbors_indices.append(10)
        else:
            neighbors_indices.append(channel - 1)
            neighbors_indices.append(channel + 1)
    
    # Vertical mirror channels: 12-23
    elif 12 <= channel <= 23:
        if channel == 12:
            neighbors_indices.append(13)
        elif channel == 23:
            neighbors_indices.append(22)
        else:
            neighbors_indices.append(channel - 1)
            neighbors_indices.append(channel + 1)
    
    # Unknown channels: 24-31
    else:
        return []
    
    return [
        getattr(bimorph.channels, f"channel{i}")
        for i in neighbors_indices
    ]


def _setup_bimorph_dofs(channel_range: range, search_radius: float = 100.0, constraint: float | None = 300.0):
    """
    Sets up the DOFs for the bimorph given a range of channels.

    Parameters
    ----------
    channel_range : range
        The range of channels to setup the DOFs for. 0-11 are horizontal mirror, 12-23 are vertical mirror, 24-31 are unknown.
    search_radius : float, optional
        How wide the search domain should be for each DOF. Default to 100.0 V.
    constraint : float | None, optional
        Constrain the search space such that each channel's distance from its neighbor is within the constraint. Default is
        300.0 V. If None, no constraint is applied. This is important for safety of the bimorph.

    Returns
    -------
    dofs : list[DOF]
        The degrees of freedom for the bimorph.
    dof_constraints : list[DOFConstraint]
        The constraints on the degrees of freedom.
    """

    dofs = []
    dof_constraints = []
    for channel in channel_range:
        bimorph_channel = getattr(bimorph.channels, f"channel{channel}")
        current_pos = bimorph_channel.readback.get()
        #current_pos = 300
        dofs.append(
            DOF(
                movable=bimorph_channel,
                type="continuous",
                #search_domain=(max(current_pos - search_radius, 0), min(current_pos + search_radius, 1200)),
                search_domain=(max(current_pos - search_radius, 0), min(current_pos + search_radius, 1200)),
            )
        )
        if constraint is not None:
            # Apply distance constraints between neighbor channels
            # Blop only supports linear constraints, so for a distance constraint, we need to apply two separate constraints.
            neighbors = _get_channel_neighbors(channel)
            for neighbor in neighbors:
                dof_constraints.append(
                    DOFConstraint(f"x1 - x2 <= {constraint}", x1=bimorph_channel, x2=neighbor)
                )
                dof_constraints.append(
                    DOFConstraint(f"x2 - x1 <= {constraint}", x1=bimorph_channel, x2=neighbor)
                )
    return dofs, dof_constraints


def _try_move_again(not_armed_mask, step, pos_cache, poll_interval):
    step_copy = step.copy()
    not_armed_channel_names = [f"bimorph_channels_channel{index + 12}" for index in np.where(not_armed_mask)]
    for channel in step_copy.keys():
        for not_armed_channel_name in not_armed_channel_names:
            if channel.name == not_armed_channel_name:
                step_copy[channel] = step_copy[channel] - 10

    # Initial fake move to dumb value
    tmp_pos_cache = copy.deepcopy(pos_cache)
    yield from bps.move_per_step(step_copy, tmp_pos_cache)
    yield from bps.sleep(poll_interval)

    # Try the real step again
    tmp_pos_cache = copy.deepcopy(pos_cache)
    yield from bps.move_per_step(step, tmp_pos_cache)
    yield from bps.sleep(poll_interval)


def _arm_bimorph(step, pos_cache, bimorph_device=None, timeout=30, tolerance=1, poll_interval=1.5):
    print(f"{timeout=}\n{poll_interval=}")
    def _armed() -> bool:
        armed_voltages = np.array(bimorph_device.all_armed_voltages()[12:24], dtype=np.float32)
        return np.allclose(armed_voltages, bimorph_device.all_setpoint_voltages()[12:24], atol=tolerance)

    copy_pos_cache = copy.deepcopy(pos_cache)
    yield from bps.move_per_step(step, pos_cache)
    while not _armed():
        yield from bps.sleep(poll_interval)
        setpoint_voltages = bimorph_device.all_setpoint_voltages()[12:24]
        armed_voltages = bimorph_device.all_armed_voltages()[12:24]
        not_armed = ~(np.abs(armed_voltages - setpoint_voltages) <= tolerance)
        invalid_mask = np.abs(armed_voltages[1:] - setpoint_voltages[:-1]) > 500.0
        invalid_mask |= np.abs(armed_voltages[:-1] - setpoint_voltages[1:]) > 500.0
        if np.any(invalid_mask):
            raise RuntimeError("Invalid configuration of the bimorph, check setpoints and adjacent armed values.")

        print(f"NOT ARMED: {not_armed}")
        print(f"NOT ARMED: {np.any(not_armed)}")

        current_voltages = bimorph_device.all_current_voltages.get()[12:24]
        invalid_mask = np.abs(current_voltages[1:] - setpoint_voltages[:-1]) > 500.0
        invalid_mask |= np.abs(current_voltages[:-1] - setpoint_voltages[1:]) > 500.0
        print(f"INVALID: {np.any(not_armed)}")
        if np.any(invalid_mask):
            yield from _ramp_bimorph(bimorph_device, timeout, tolerance, poll_interval)
            yield from bps.sleep(poll_interval)
            if np.any(not_armed):
                print(f"MOVING AGAIN (INVALID): {not_armed}")
                print(f"MOVING AGAIN (INVALID): {step}")
                yield from _try_move_again(not_armed, step, copy_pos_cache, poll_interval)
        elif np.any(not_armed):
            print(f"MOVING AGAIN (INVALID): {not_armed}")
            print(f"MOVING AGAIN (ALL VALID): {step}")
            yield from _try_move_again(not_armed, step, copy_pos_cache, poll_interval)


# 1. Choose setpoints
# 2. Check armed against setpoints
# 3. If failure, check armed - 1 against setpoints
# 4. If 3 succeeds, check armed + 1 against setpoints
# 5. If armed is all fine, check current against setpoints
# 6. If 5 succeeds, check current - 1 against setpoints
# 7. If 6 succeeds, check current + 1 against setpoints

# 8. If current fails and armed succeeds, then ramp, then go to 1
# 9. If armed failed, 

# def _arm_bimorph(step, pos_cache, bimorph_device=None, timeout=10, tolerance=1, poll_interval=0.1):
#     def _armed() -> bool:
#         armed_voltages = np.array(bimorph_device.all_armed_voltages()[12:24], dtype=np.float32)
#         return np.allclose(armed_voltages, bimorph_device.all_setpoint_voltages()[12:24], atol=tolerance)
# 
#     # Move to the next position (change setpoints for bimorph channels)
#     copy_pos_cache = pos_cache.copy()
#     yield from bps.move_per_step(step, pos_cache)
# 
#     # Wait for the bimorph mirror to be armed
#     start_time = ttime.monotonic()
#     while not _armed():
#         yield from bps.sleep(poll_interval)
#         copy_pos_cache = copy_pos_cache.copy()
#         yield from bps.move_per_step(step, copy_pos_cache)
#         yield from bps.sleep(poll_interval)
#         end_time = ttime.monotonic()
#         if end_time - start_time > timeout:
#             raise TimeoutError(f"Failed to arm the bimorph mirrors within {timeout} seconds")

def _ramp_bimorph(bimorph_device=None, timeout=10, tolerance=1, poll_interval=0.5):
    def _ramped() -> bool:
        current_voltages = np.array(bimorph_device.all_current_voltages.get()[12:24], dtype=np.float32)
        return np.allclose(current_voltages, bimorph_device.all_setpoint_voltages()[12:24], atol=tolerance)
    
    # Start ramping
    yield from bimorph_device.start_plan()

    # Wait for the bimorph mirror to be ramped
    start_time = ttime.monotonic()
    while not _ramped():
        yield from bps.sleep(poll_interval)
        if ttime.monotonic() - start_time > timeout:
            raise TimeoutError(f"Failed to ramp the bimorph mirrors within {timeout} seconds")

    # settle time after ramping
    yield from bps.sleep(1.0)


def one_nd_bimorph_step(detectors, step, pos_cache, take_reading=None, *, bimorph_device=None, timeout=60, tolerance=1, poll_interval=5.0):
    """
    Per-step hook that allows for coordinated movement of the bimorph mirrors.
    
    The bimorph mirror system requires that the actuators be armed, then ramped to the target voltages.
    Setting an individual channel (actuator) only sets the target voltage for that channel.

    Parameters
    ----------
    detectors : list[Readable]
        The detectors to take a reading from
    step : dict[NamedMovable, Any]
        The next position to move to for each movable device
    pos_cache : dict[NamedMovable, Any]
        The last position moved to for each movable device
    take_reading : Callable[[list[Readable]], MsgGenerator] | None, optional
        Custom plan hook to take a reading from the detectors, defaults to ``bps.trigger_and_read``
    bimorph : Bimorph | None, optional
        The bimorph mirror system to control, default to ``bimorph`` device defined in the namespace
    timeout : float, optional
        The timeout for the bimorph to arm and ramp, default to 10 seconds
    tolerance : float, optional
        The tolerance for each channel's residual voltage to be within, default to 1 V
    poll_interval : float, optional
        The interval to poll the bimorph to arm and ramp, default to 0.001 seconds
    """

    if take_reading is None:
        take_reading = bps.trigger_and_read
    
    if bimorph_device is None:
        bimorph_device = bimorph

    yield from _arm_bimorph(
        step,
        pos_cache,
        bimorph_device=bimorph_device,
        timeout=timeout,
        tolerance=tolerance,
        poll_interval=poll_interval,
    )

    # Actual ramp to the setpoint
    yield from _ramp_bimorph(bimorph_device, timeout, tolerance, poll_interval)

    # Take a reading from the detectors
    yield from take_reading(list(detectors) + list(step.keys()))


vertical_mirror_dofs, vertical_mirror_dof_constraints = _setup_bimorph_dofs(
    range(12, 24),
    search_radius=250.0,
    constraint=490.0,
)
uniform_vertical_profile_objectives = [
    Objective(name="vertical_coefficient_variation", target="min"),
    Objective(name="total_vertical_intensity", target="max"),
]
uniform_vertical_profile_agent = AxAgent(
    readables=optimization_detectors,
    dofs=vertical_mirror_dofs,
    objectives=uniform_vertical_profile_objectives,
    evaluation=vertical_profile_digestion,
    dof_constraints=vertical_mirror_dof_constraints,
    acquisition_plan=functools.partial(default_acquire, per_step=one_nd_bimorph_step),
)
uniform_vertical_profile_agent.ax_client.configure_generation_strategy(
    initialization_budget=15,
    initialize_with_center=False,
    allow_exceeding_initialization_budget=True,
)
optimization_problem = uniform_vertical_profile_agent.to_optimization_problem()

@plan
def optimize_step(
    optimization_problem: OptimizationProblem,
    n_points: int = 1,
    *args: Any,
    **kwargs: Any,
) -> MsgGenerator[None]:
    """
    A single step of the optimization loop.

    Parameters
    ----------
    optimization_problem : OptimizationProblem
        The optimization problem to solve.
    n_points : int, optional
        The number of points to suggest.
    """
    if optimization_problem.acquisition_plan is None:
        acquisition_plan = default_acquire
    else:
        acquisition_plan = optimization_problem.acquisition_plan
    optimizer = optimization_problem.optimizer
    movables = optimization_problem.movables
    suggestions = optimizer.suggest(n_points)
    #_ = yield from bps.input_plan(f"{suggestions=}")
    uid = yield from acquisition_plan(suggestions, movables, optimization_problem.readables, *args, **kwargs)
    outcomes = optimization_problem.evaluation_function(uid, suggestions)
    optimizer.ingest(outcomes)


@plan
def optimize(
    optimization_problem: OptimizationProblem,
    iterations: int = 1,
    n_points: int = 1,
    *args: Any,
    **kwargs: Any,
) -> MsgGenerator[None]:
    """
    A plan to solve the optimization problem.

    Parameters
    ----------
    optimization_problem : OptimizationProblem
        The optimization problem to solve.
    iterations : int, optional
        The number of optimization iterations to run.
    n_points : int, optional
        The number of points to suggest per iteration.
    """

    for _ in range(iterations):
        yield from optimize_step(optimization_problem, n_points, *args, **kwargs)

