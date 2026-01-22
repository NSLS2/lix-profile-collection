import numpy as np
import time as ttime
import bluesky.plan_stubs as bps


def get_channel_neighbor_indices(channel: int) -> list[int]:
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
    channel_indices = get_channel_neighbor_indices(channel_idx) + [channel_idx]
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
    neighbor_indices = get_channel_neighbor_indices(channel_idx)
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
            list(target_voltages.keys()),
            timeout=timeout,
            wait_interval=wait_interval,
            tolerance=tolerance,
        )
    
    if iteration >= max_iterations:
        raise RuntimeError(f"Bimorph arm and ramp operation exceeded maximum iterations ({max_iterations})")


def one_bimorph_step(detectors, step, pos_cache, take_reading=None, *, bimorph_device=None, timeout=60, tolerance=1):
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

