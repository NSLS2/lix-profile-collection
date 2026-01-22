import functools
import time as ttime
from typing import Any
import cv2

from bluesky.utils import MsgGenerator
import bluesky.plan_stubs as bps
import numpy as np

from blop import DOF, Objective, Agent
from blop.plans import default_acquire
from blop.ax.dof import DOFConstraint
from blop.protocols import OptimizationProblem

import numpy as np


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


def _get_channel_neighbor_indices(channel: int) -> list[int]:
    """Helper function to get the indices of the neighbors of a channel in the bimorph."""
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
    
    return neighbors_indices


def _get_channel_neighbors(channel: int) -> list[Channel]:
    """Helper function to get the neighbors of a channel in the bimorph."""
    return [
        getattr(bimorph.channels, f"channel{i}")
        for i in _get_channel_neighbor_indices(channel)
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

def _check_channel_constraint(channel_idx, target_voltage, current_values, armed_values, max_distance=500.0):
    """
    Check if setting channel to target voltage would violate constraint with adjacent channels.
    
    Parameters
    ----------
    channel_idx : int
        Channel index (0-11 is for horizontal mirror, 12-23 is for vertical mirror)
    target_voltage : float
        Target voltage to check
    current_values : np.ndarray
        Current voltage values for all channels
    armed_values : np.ndarray
        Armed voltage values for all channels
    max_distance : float, optional
        Maximum allowed distance between adjacent channels (default 500.0 V)
    
    Returns
    -------
    bool
        True if safe (no constraint violation), False if would violate constraint
    """
    channel_indices = _get_channel_neighbor_indices(channel_idx) + [channel_idx]
    for idx in channel_indices:
        if (abs(target_voltage - current_values[idx]) > max_distance or
            abs(target_voltage - armed_values[idx]) > max_distance):
            return False
    return True


def _calculate_intermediate_step(channel_idx, current_voltage, target_voltage, current_values, armed_values, 
                                 max_distance=500.0, step_limit=400.0):
    """
    Calculate intermediate step value for channel that would violate constraint.
    
    Parameters
    ----------
    channel_idx : int
        Channel index (12-23 for vertical mirror)
    current_voltage : float
        Current voltage of this channel
    target_voltage : float
        Target voltage for this channel
    current_values : np.ndarray
        Current voltage values for all channels (12-23)
    armed_values : np.ndarray
        Armed voltage values for all channels (12-23)
    max_distance : float, optional
        Maximum allowed distance between adjacent channels (default 500.0 V)
    step_limit : float, optional
        Maximum step size (default 400.0 V)
    
    Returns
    -------
    float
        Intermediate voltage value that respects constraint and step limit
    """
    # Calculate direction of movement
    direction = 1.0 if target_voltage > current_voltage else -1.0
    voltage_diff = abs(target_voltage - current_voltage)
    
    # 1. Start with step limit constraint
    step = min(voltage_diff, step_limit)

    # 2. Check constraint with neighbors
    neighbor_indices = _get_channel_neighbor_indices(channel_idx)
    for idx in neighbor_indices:
        distance_current = abs(target_voltage - current_values[idx])
        distance_armed = abs(target_voltage - armed_values[idx])
        # Pick the furthest distance from the target update the max step we can take
        if distance_current >= distance_armed:
            step = min(step, (current_values[idx] + direction * max_distance) - current_voltage)
        else:
            step = min(step, (armed_values[idx] + direction * max_distance) - current_voltage)

    # Calculate the new voltage setpoint (either full or partial step)
    voltage_step = direction * step
    candidate_voltage = current_voltage + voltage_step

    return candidate_voltage


def _wait_for_channel_armed(channel, target_value, timeout=10.0, tolerance=1.0, poll_interval=0.1):
    """
    Wait until channel's armed value matches target value.
    
    Parameters
    ----------
    channel : Channel
        Bimorph channel object
    target_value : float
        Target value to wait for
    timeout : float, optional
        Maximum time to wait (default 10.0 seconds)
    tolerance : float, optional
        Tolerance for matching (default 1.0 V)
    poll_interval : float, optional
        Polling interval (default 0.1 seconds)
    
    Yields
    ------
    Msg
        Bluesky messages
    """
    start_time = ttime.monotonic()
    while True:
        armed_value = channel.armed_voltage.get()
        if abs(armed_value - target_value) <= tolerance:
            break
        
        if ttime.monotonic() - start_time > timeout:
            raise TimeoutError(
                f"Timeout waiting for channel {channel.name} armed value to reach {target_value} "
                f"(current: {armed_value})"
            )
        
        yield from bps.sleep(poll_interval)


def _ramp_all_channels(bimorph_device, channel_indices, timeout=60, wait_interval=5.0, tolerance=1.0, poll_interval=0.1):
    """
    Ramp all channels (armed values to current values).
    
    Parameters
    ----------
    bimorph_device : Bimorph
        Bimorph device
    channel_indices : list[int]
        The indices of the channels to ramp
    timeout : float, optional
        Maximum time to wait for ramp to complete (default 60 seconds)
    wait_interval : float, optional
        Wait time after ramp completes (default 5.0 seconds)
    tolerance : float, optional
        Tolerance for matching voltages (default 1.0 V)
    poll_interval : float, optional
        Polling interval (default 0.1 seconds)
    
    Yields
    ------
    Msg
        Bluesky messages
    """
    def _ramped() -> bool:
        current_voltages = np.array(bimorph_device.all_current_voltages.get()[channel_indices], dtype=np.float32)    
        return np.allclose(current_voltages, bimorph_device.all_setpoint_voltages()[channel_indices], atol=tolerance)

    # Start ramping
    yield from bimorph_device.start_plan()

    # Wait for the bimorph mirror to be ramped
    start_time = ttime.monotonic()
    while not _ramped():
        yield from bps.sleep(poll_interval)
        if ttime.monotonic() - start_time > timeout:
            raise TimeoutError(f"Failed to ramp the bimorph mirrors within {timeout} seconds")
    
    # Wait additional time after ramping
    yield from bps.sleep(wait_interval)


def _arm_and_ramp_bimorph(step, pos_cache, bimorph_device=None, timeout=60, tolerance=1.0, 
                           max_distance=500.0, step_limit=400.0, wait_interval=5.0):
    """
    Arm and ramp bimorph channels using sequential setting with constraint checking.
    
    Parameters
    ----------
    step : dict[NamedMovable, Any]
        Dictionary mapping channel objects to target voltages
    pos_cache : dict[NamedMovable, Any]
        Position cache (not used in this implementation but kept for compatibility)
    bimorph_device : Bimorph, optional
        Bimorph device (defaults to global `bimorph`)
    timeout : float, optional
        Overall timeout for the operation (default 60 seconds)
    tolerance : float, optional
        Tolerance for matching voltages (default 1.0 V)
    max_distance : float, optional
        Maximum distance between adjacent channels (default 500.0 V)
    step_limit : float, optional
        Maximum step size when calculating intermediate steps (default 400.0 V)
    wait_interval : float, optional
        Wait time after all channels are armed and after ramping (default 5.0 seconds)
    
    Yields
    ------
    Msg
        Bluesky messages
    """
    if bimorph_device is None and "bimorph" in globals():
        bimorph_device = bimorph
    
    # Extract target voltages for channels 12-23
    # step dictionary has channel objects as keys
    target_voltages = {}
    for channel_obj, target_value in step.items():
        # Extract channel number from channel name (e.g., "bimorph_channels_channel12" -> 12)
        if hasattr(channel_obj, 'name'):
            channel_name = channel_obj.name
            if 'channel' in channel_name:
                channel_num = int(channel_name.split('channel')[-1])
                target_voltages[channel_num] = (channel_obj, target_value)
    
    # Sort channels by number (12, 13, 14, ..., 23)
    sorted_channels = sorted(target_voltages.items())

    # Main loop: repeat until all channels reach target
    max_iterations = 20  # Prevent infinite loops
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Get current state
        current_values = np.array(bimorph_device.all_current_voltages.get(), dtype=np.float32)
        armed_values = np.array(bimorph_device.all_armed_voltages(), dtype=np.float32)
        
        # Check if we're done (all channels at target)
        all_at_target = True
        for channel_num, (channel_obj, target_value) in sorted_channels:
            if abs(current_values[channel_num] - target_value) > tolerance:
                all_at_target = False
                break
        
        # Success - Exit when all channels are at target
        if all_at_target:
            break 
        
        # Arm channels in order, to a safe value, one at a time
        for channel_num, (channel_obj, target_value) in sorted_channels:
            # Check if constraint would be violated
            constraint_ok = _check_channel_constraint(
                channel_num, target_value, current_values, armed_values, max_distance
            )
            
            if constraint_ok:
                # Set directly to target
                set_value = target_value
            else:
                # Calculate intermediate step
                set_value = _calculate_intermediate_step(
                    channel_num, target_value, current_values, armed_values,
                    max_distance, step_limit
                )

            # Only set if the value is different from the current value
            # Otherwise, we are already at the target or we can
            #   return to this channel on the next iteration
            if set_value != current_values[channel_num]:
                # Set channel to value (intermediate or target)
                yield from bps.mv(channel_obj, set_value)
                
                # Wait for this channel's armed value to match the setpoint
                yield from _wait_for_channel_armed(
                    channel_obj, set_value, timeout, tolerance
                )
            
                # Update armed values for next channel's constraint check
                armed_values = np.array(bimorph_device.all_armed_voltages(), dtype=np.float32)
        
        # Wait after all channels are armed
        yield from bps.sleep(wait_interval)
        
        # Ramp all channels
        yield from _ramp_all_channels(
            bimorph_device,
            target_voltages.keys(),
            timeout=timeout,
            wait_interval=wait_interval,
            tolerance=tolerance,
        )
    
    if iteration >= max_iterations:
        raise RuntimeError(f"Bimorph arm and ramp operation exceeded maximum iterations ({max_iterations})")


def one_nd_bimorph_step(detectors, step, pos_cache, take_reading=None, *, bimorph_device=None, timeout=60, tolerance=1):
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
    bimorph_device : Bimorph | None, optional
        The bimorph mirror system to control, default to ``bimorph`` device defined in the namespace
    timeout : float, optional
        The timeout for the bimorph to arm and ramp, default to 60 seconds
    tolerance : float, optional
        The tolerance for each channel's residual voltage to be within, default to 1 V
    """

    if take_reading is None:
        take_reading = bps.trigger_and_read
    
    if bimorph_device is None and "bimorph" in globals():
        bimorph_device = bimorph

    # Use new algorithm that handles sequential setting, constraint checking, and ramping
    yield from _arm_and_ramp_bimorph(
        step,
        pos_cache,
        bimorph_device=bimorph_device,
        timeout=timeout,
        tolerance=tolerance,
    )

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
uniform_vertical_profile_agent = Agent(
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

