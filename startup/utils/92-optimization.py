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
    
    metrics_dict = {
        'cv': cv,
        'total_intensity': total_intensity,
        'mean_intensity': mean_intensity,
        'std_intensity': std_intensity,
        'vertical_profile': vertical_profile
    }
    
    return 0.0, None, metrics_dict

optimization_detectors = [
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

