"""
Replay script for Bluesky optimization experiments.

This script replays camSF-based optimization runs from tiled Run UIDs,
displaying live detector images and objective metric plots.
"""

import numpy as np
import matplotlib.pyplot as plt
import time as ttime
from ophyd import Device, Signal
from ophyd.sim import NullStatus
from bluesky.callbacks.core import CallbackBase
import bluesky.plan_stubs as bps
from bluesky.plan_stubs import open_run, close_run, trigger_and_read
from tiled.client import from_uri, from_profile
from tiled.server import SimpleTiledServer
import cv2


lix_client = from_uri("https://tiled.nsls2.bnl.gov/")["lix"]["raw"]

# Import intensity_metric from 60-utils
# We'll copy it here to avoid import issues
def intensity_metric(image, background=None, threshold_factor=0.4, edge_crop=0):
    """Calculate beam intensity from image."""
    # Convert to grayscale
    image = image.squeeze()
    if len(image.shape) == 3 and image.shape[0] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # crop the image to remove noise around the edges
    gray = gray[200:500, 800:1100]

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
        return float('inf')
        
    thresh_value = threshold_factor * max_intensity
    _, thresh = cv2.threshold(corrected, thresh_value, 255, cv2.THRESH_TOZERO)
    
    # Total integrated intensity
    total_intensity = np.sum(thresh)
    
    return total_intensity


class ReplayMotor(Device):
    """Mock motor device that replays pre-recorded positions."""
    
    def __init__(self, name, positions, timestamps, debug=False):
        super().__init__(name=name)
        self.positions = positions
        self.timestamps = timestamps
        self._current_idx = 0
        self.debug = debug
        self._position = Signal(name=f"{name}_position", value=positions[0] if len(positions) > 0 else 0.0)
        if self.debug:
            print(f"[DEBUG] Created ReplayMotor {name} with {len(positions)} positions")
        
    @property
    def position(self):
        """Current position."""
        if self._current_idx < len(self.positions):
            return self.positions[self._current_idx]
        return self.positions[-1] if len(self.positions) > 0 else 0.0
    
    def set(self, value):
        """Set position (immediate, no hardware delay)."""
        # Find closest position in sequence
        if len(self.positions) > 0:
            idx = min(range(len(self.positions)), key=lambda i: abs(self.positions[i] - value))
            self._current_idx = idx
            self._position.put(value)
            if self.debug:
                print(f"[DEBUG] {self.name}.set({value}) -> idx={idx}, actual={self.positions[idx]}")
        return NullStatus()
    
    def move(self, value):
        """Move to position."""
        if self.debug:
            print(f"[DEBUG] {self.name}.move({value})")
        return self.set(value)
    
    def read(self):
        """Read current position."""
        pos = self.position
        if self.debug:
            print(f"[DEBUG] {self.name}.read() -> {pos}")
        return {f"{self.name}_position": {"value": pos, "timestamp": ttime.time()}}
    
    def describe(self):
        """Describe the device."""
        return {f"{self.name}_position": {
            "source": "replay_motor",
            "dtype": "number",
            "shape": [],
            "precision": 3
        }}
    
    def advance(self):
        """Advance to next position in sequence."""
        if self._current_idx < len(self.positions) - 1:
            self._current_idx += 1
            self._position.put(self.positions[self._current_idx])


class ReplayDetector(Device):
    """Mock detector device that replays pre-recorded images."""
    
    def __init__(self, name, images, timestamps, debug=False):
        super().__init__(name=name)
        self.images = images
        self.timestamps = timestamps
        self._current_idx = 0
        self.debug = debug
        if self.debug:
            print(f"[DEBUG] Created ReplayDetector {name} with {len(images)} images")
            if len(images) > 0:
                print(f"[DEBUG]   First image shape: {images[0].shape}")
        
    @property
    def current_image(self):
        """Get current image."""
        if self._current_idx < len(self.images):
            return self.images[self._current_idx]
        return self.images[-1] if len(self.images) > 0 else np.zeros((100, 100))
    
    def read(self):
        """Read current image."""
        img = self.current_image
        if self.debug:
            print(f"[DEBUG] {self.name}.read() -> idx={self._current_idx}, shape={img.shape}")
        return {f"{self.name}_image": {"value": img, "timestamp": ttime.time()}}
    
    def describe(self):
        """Describe the device."""
        if len(self.images) > 0:
            img_shape = self.images[0].shape
        else:
            img_shape = (100, 100)
        return {f"{self.name}_image": {
            "source": "replay_detector",
            "dtype": "array",
            "shape": img_shape
        }}
    
    def trigger(self):
        """Trigger detector (no-op for replay)."""
        if self.debug:
            print(f"[DEBUG] {self.name}.trigger() called")
        return NullStatus()
    
    def advance(self):
        """Advance to next image in sequence."""
        if self._current_idx < len(self.images) - 1:
            self._current_idx += 1
            if self.debug:
                print(f"[DEBUG] {self.name}.advance() -> idx={self._current_idx}")


class ReplayVisualizer(CallbackBase):
    """Visualization callback for replay."""
    
    def __init__(self, detector_name="camSF", debug=False):
        super().__init__()
        self.detector_name = detector_name
        self.debug = debug
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        # Top plot: objective metric
        self.ax1.set_xlabel("Step")
        self.ax1.set_ylabel("Beam Intensity (×10⁶)")
        self.ax1.set_title("Objective Metric")
        self.ax1.grid(True)
        self.intensity_data = []
        self.step_data = []
        self.line, = self.ax1.plot([], [], 'b-o', markersize=4)
        
        # Bottom plot: detector image
        self.ax2.set_title("Detector Image")
        self.ax2.set_xlabel("X (pixels)")
        self.ax2.set_ylabel("Y (pixels)")
        self.im = None
        
        plt.tight_layout()
        plt.ion()
        plt.show(block=False)
        
        # Force initial draw
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer initialized for detector '{detector_name}'")
            print(f"[DEBUG]   Figure created: {self.fig}")
            print(f"[DEBUG]   Axes: {self.ax1}, {self.ax2}")
    
    def start(self, doc):
        """Initialize on run start."""
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer.start() called")
            print(f"[DEBUG]   Run UID: {doc.get('uid', 'N/A')}")
            print(f"[DEBUG]   Detectors: {doc.get('detectors', [])}")
        self.intensity_data = []
        self.step_data = []
        self.line.set_data([], [])
        self.ax1.clear()
        self.ax1.set_xlabel("Step")
        self.ax1.set_ylabel("Beam Intensity (×10⁶)")
        self.ax1.set_title("Objective Metric")
        self.ax1.grid(True)
        self.line, = self.ax1.plot([], [], 'b-o', markersize=4)
        self.ax1.relim()
        self.ax1.autoscale_view()
        
        # Clear image plot
        self.ax2.clear()
        self.ax2.set_title("Detector Image")
        self.ax2.set_xlabel("X (pixels)")
        self.ax2.set_ylabel("Y (pixels)")
        self.im = None
        
        # Force redraw
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        super().start(doc)
    
    def event(self, doc):
        """Update plots on each event."""
        if self.debug:
            seq_num = doc.get('seq_num', 'N/A')
            print(f"[DEBUG] ReplayVisualizer.event() called - seq_num={seq_num}")
        
        data = doc.get('data', {})
        
        if self.debug:
            print(f"[DEBUG]   Event data keys: {list(data.keys())}")
        
        # Get image from detector - handle both direct value and dict with 'value' key
        image_key = f"{self.detector_name}_image"
        if image_key in data:
            if self.debug:
                print(f"[DEBUG]   Found image key: {image_key}")
            image_data = data[image_key]
            # Handle both direct array and dict with 'value' key
            if isinstance(image_data, dict):
                image = image_data.get('value', image_data)
                if self.debug:
                    print(f"[DEBUG]   Extracted image from dict, shape={image.shape if hasattr(image, 'shape') else 'unknown'}")
            else:
                image = image_data
                if self.debug:
                    print(f"[DEBUG]   Image is direct array, shape={image.shape if hasattr(image, 'shape') else 'unknown'}")
            
            # Ensure image is numpy array
            if not isinstance(image, np.ndarray):
                image = np.array(image)
            
            if self.debug:
                print(f"[DEBUG]   Final image shape: {image.shape}, dtype={image.dtype}")
            
            # Calculate intensity metric
            intensity = intensity_metric(image.transpose(1, 0))
            intensity_millions = intensity
            
            if self.debug:
                print(f"[DEBUG]   Calculated intensity: {intensity_millions:.2f} (×10⁶)")
            
            # Update intensity plot
            step_num = doc.get('seq_num', len(self.step_data))
            self.step_data.append(step_num)
            self.intensity_data.append(intensity_millions)
            
            # Convert to numpy arrays for set_data
            step_array = np.array(self.step_data)
            intensity_array = np.array(self.intensity_data)
            
            self.line.set_data(step_array, intensity_array)
            self.ax1.relim()
            self.ax1.autoscale_view()
            
            # Update image display
            if self.im is None:
                if self.debug:
                    print(f"[DEBUG]   Creating initial image display")
                # Ensure image is 2D
                if len(image.shape) > 2:
                    image = image.squeeze()
                    if len(image.shape) > 2:
                        # Take first channel if still 3D
                        image = image[0] if image.shape[0] < image.shape[1] else image[:, :, 0]
                
                self.im = self.ax2.imshow(image, cmap='gray', aspect='auto', interpolation='nearest')
                self.ax2.set_xlim(-0.5, image.shape[1] - 0.5)
                self.ax2.set_ylim(image.shape[0] - 0.5, -0.5)  # Flip y-axis for image coordinates
                self.fig.colorbar(self.im, ax=self.ax2)
            else:
                if self.debug:
                    print(f"[DEBUG]   Updating image display")
                # Ensure image is 2D
                if len(image.shape) > 2:
                    image = image.squeeze()
                    if len(image.shape) > 2:
                        image = image[0] if image.shape[0] < image.shape[1] else image[:, :, 0]
                
                self.im.set_data(image)
                # Update color limits for better visualization
                img_min, img_max = image.min(), image.max()
                if img_max > img_min:
                    self.im.set_clim(vmin=img_min, vmax=img_max)
            
            # Force redraw - use draw() for immediate update
            try:
                self.fig.canvas.draw()
                self.fig.canvas.flush_events()
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG]   Canvas draw error: {e}")
                # Fallback to draw_idle
                self.fig.canvas.draw_idle()
                self.fig.canvas.flush_events()
        else:
            if self.debug:
                print(f"[DEBUG]   Image key '{image_key}' not found in event data")
        
        super().event(doc)
    
    def stop(self, doc):
        """Finalize on run stop."""
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer.stop() called")
            print(f"[DEBUG]   Total events processed: {len(self.step_data)}")
        super().stop(doc)


def extract_run_data(uids, tiled_client=None, debug=False):
    """
    Extract data from tiled runs, preserving per-run structure.
    
    Parameters
    ----------
    uids : list of str
        List of Run UIDs to extract data from
    tiled_client : tiled client, optional
        Tiled client instance. If None, uses lix_client
    
    Returns
    -------
    list
        List of run data dictionaries, each containing:
        - 'uid': Run UID
        - 'motor_positions': dict with keys for motors that were controlled (e.g., 'crl_x1', 'crl_x2', etc.)
        - 'images': array of detector images
        - 'timestamps': array of timestamps
        - 'beam_intensities': array of calculated beam intensities
        - 'motors_controlled': list of motor keys that were controlled in this run
    """
    if debug:
        print(f"[DEBUG] extract_run_data: Processing {len(uids)} UIDs")
        if tiled_client is None:
            print(f"[DEBUG]   Using default lix_client")
        else:
            print(f"[DEBUG]   Using provided tiled_client")
    
    runs_data = []
    
    for idx, uid in enumerate(uids):
        if debug:
            print(f"[DEBUG] Processing run {idx+1}/{len(uids)}: {uid}")
        try:
            run = tiled_client[uid]
            
            if debug:
                print(f"[DEBUG]   Successfully loaded run")
                print(f"[DEBUG]   Run metadata keys: {list(run.metadata.keys())}")
            
            # Get primary data stream
            primary_data = run["primary/data"]
            
            if debug:
                print(f"[DEBUG]   Primary data keys: {list(primary_data.keys())}")
            
            # Try to get motor positions - only extract motors that exist in this run
            motor_field_names = {
                'crl_x1': ['crl_x1'],
                'crl_x2': ['crl_x2'],
                'crl_y1': ['crl_y1'],
                'crl_y2': ['crl_y2']
            }
            
            run_motor_positions = {}
            motors_controlled = []
            
            for motor_key, field_variants in motor_field_names.items():
                for field_name in field_variants:
                    try:
                        if debug:
                            print(f"[DEBUG]   Trying motor field: {field_name}")
                        data = primary_data[field_name].read()
                        if debug:
                            print(f"[DEBUG]     Found! Type: {type(data)}, shape: {getattr(data, 'shape', 'N/A')}")
                        # Handle both array and scalar cases
                        if hasattr(data, '__len__') and not isinstance(data, str):
                            if hasattr(data, 'shape') and len(data.shape) > 0:
                                run_motor_positions[motor_key] = data.tolist()
                                if debug:
                                    print(f"[DEBUG]     Extracted {len(data)} values")
                            else:
                                run_motor_positions[motor_key] = list(data)
                                if debug:
                                    print(f"[DEBUG]     Extracted {len(data)} values (list)")
                        else:
                            run_motor_positions[motor_key] = [float(data)]
                            if debug:
                                print(f"[DEBUG]     Extracted 1 scalar value: {data}")
                        motors_controlled.append(motor_key)
                        break
                    except (KeyError, AttributeError) as e:
                        if debug:
                            print(f"[DEBUG]     Field {field_name} not found: {e}")
                        continue
            
            if debug:
                print(f"[DEBUG]   Motors controlled in this run: {motors_controlled}")
                for key, values in run_motor_positions.items():
                    if values:
                        print(f"[DEBUG]     {key}: {len(values)} values, range=[{min(values):.3f}, {max(values):.3f}]")
            
            # Get detector images - try camSF first, then check metadata
            images_found = False
            image_field_variants = ['camSF_image']
            
            if debug:
                print(f"[DEBUG]   Looking for image data...")
            
            for field_name in image_field_variants:
                try:
                    if debug:
                        print(f"[DEBUG]     Trying image field: {field_name}")
                    images = primary_data[field_name].read().squeeze()
                    if debug:
                        print(f"[DEBUG]       Found! Shape: {images.shape}, dtype: {images.dtype}")
                    images_found = True
                    break
                except (KeyError, AttributeError) as e:
                    if debug:
                        print(f"[DEBUG]       Field {field_name} not found: {e}")
                    continue
            
            if not images_found:
                # Try to get camera name from metadata
                if debug:
                    print(f"[DEBUG]     Trying metadata approach...")
                try:
                    start_md = run.metadata.get("start", {})
                    detectors = start_md.get("detectors", [])
                    if debug:
                        print(f"[DEBUG]       Detectors from metadata: {detectors}")
                    if detectors:
                        cam_name = detectors[0]
                        images = primary_data[f"{cam_name}_image"].read()
                        if debug:
                            print(f"[DEBUG]       Found via metadata! Shape: {images.shape}")
                        images_found = True
                except Exception as e:
                    if debug:
                        print(f"[DEBUG]       Metadata approach failed: {e}")
                    pass
            
            run_images = []
            run_intensities = []
            
            if images_found:
                # Handle different image array shapes
                if hasattr(images, 'shape'):
                    if debug:
                        print(f"[DEBUG]     Processing images with shape: {images.shape}")
                    if len(images.shape) == 3:
                        # Multiple images (n_images, height, width) - leading dim is events
                        if debug:
                            print(f"[DEBUG]       Extracting {images.shape[0]} images from 3D array (events x height x width)")
                        for i in range(images.shape[0]):
                            img = images[i].copy()  # Make a copy to avoid reference sharing!
                            run_images.append(img)
                            intensity = intensity_metric(img)
                            run_intensities.append(intensity)
                            if debug and i < 3:
                                img_hash = hash(img.tobytes()[:1000])
                                print(f"[DEBUG]         Event {i}: shape={img.shape}, intensity={intensity:.2f}, hash={img_hash}")
                    elif len(images.shape) == 2:
                        # Single image (height, width) - this is event 0
                        if debug:
                            print(f"[DEBUG]       Single 2D image (single event)")
                        img = images.copy()  # Make a copy to avoid reference sharing!
                        run_images.append(img)
                        intensity = intensity_metric(img)
                        run_intensities.append(intensity)
                        if debug:
                            img_hash = hash(img.tobytes()[:1000])
                            print(f"[DEBUG]         Event 0: intensity={intensity:.2f}, hash={img_hash}")
                    else:
                        print(f"Warning: Unexpected image shape {images.shape} in run {uid}")
                else:
                    # Single image as array-like
                    if debug:
                        print(f"[DEBUG]     Converting array-like to numpy array")
                    images_array = np.array(images).copy()  # Make a copy!
                    run_images.append(images_array)
                    intensity = intensity_metric(images_array)
                    run_intensities.append(intensity)
                    if debug:
                        img_hash = hash(images_array.tobytes()[:1000])
                        print(f"[DEBUG]       Event 0: intensity={intensity:.2f}, hash={img_hash}")
            else:
                print(f"Warning: Could not find image data in run {uid}")
                continue  # Skip runs without images
            
            # Get timestamps
            try:
                timestamps = primary_data["time"].read()
                if hasattr(timestamps, '__len__') and not isinstance(timestamps, str):
                    if hasattr(timestamps, 'shape') and len(timestamps.shape) > 0:
                        run_timestamps = timestamps.tolist()
                    else:
                        run_timestamps = list(timestamps)
                else:
                    run_timestamps = [float(timestamps)]
            except (KeyError, AttributeError):
                # Generate timestamps if not available
                num_events = len(run_images)
                base_time = ttime.time() if idx == 0 else runs_data[-1]['timestamps'][-1] + 1.0
                run_timestamps = [base_time + i * 0.5 for i in range(num_events)]
            
            # Ensure timestamps match number of images
            if len(run_timestamps) != len(run_images):
                if len(run_timestamps) == 1 and len(run_images) > 1:
                    # Expand single timestamp
                    base_time = run_timestamps[0]
                    run_timestamps = [base_time + i * 0.5 for i in range(len(run_images))]
                elif len(run_timestamps) > len(run_images):
                    run_timestamps = run_timestamps[:len(run_images)]
                else:
                    # Pad timestamps
                    last_time = run_timestamps[-1] if run_timestamps else ttime.time()
                    run_timestamps.extend([last_time + (i+1) * 0.5 for i in range(len(run_images) - len(run_timestamps))])
            
            # Store run data
            runs_data.append({
                'uid': uid,
                'motor_positions': run_motor_positions,
                'motors_controlled': motors_controlled,
                'images': np.array(run_images),
                'timestamps': np.array(run_timestamps),
                'beam_intensities': np.array(run_intensities)
            })
            
            if debug:
                print(f"[DEBUG]   Run {idx+1} complete: {len(run_images)} images, {len(motors_controlled)} motors")
        
        except Exception as e:
            print(f"Error processing run {uid}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if len(runs_data) == 0:
        raise ValueError("No data extracted from any runs!")
    
    if debug:
        print(f"[DEBUG] Data extraction summary:")
        print(f"[DEBUG]   Total runs processed: {len(runs_data)}")
        for idx, run_data in enumerate(runs_data):
            print(f"[DEBUG]   Run {idx+1}: {len(run_data['images'])} images, motors={run_data['motors_controlled']}")
    
    return runs_data


def create_replay_plan(motors, detector, runs_data, speed_multiplier=1.0, debug=False):
    """
    Create a Bluesky plan that replays the optimization sequence run by run.
    
    Parameters
    ----------
    motors : dict
        Dictionary with keys 'x1', 'x2', 'y1', 'y2' containing ReplayMotor instances (may be None)
    detector : ReplayDetector
        Replay detector instance
    runs_data : list
        List of run data dictionaries from extract_run_data
    speed_multiplier : float
        Speed multiplier for replay (1.0 = real-time)
    debug : bool
        Enable debug print statements
    
    Yields
    ------
    Bluesky plan messages
    """
    motor_map = {
        'crl_x1': 'x1',
        'crl_x2': 'x2',
        'crl_y1': 'y1',
        'crl_y2': 'y2'
    }
    
    total_steps = sum(len(run['images']) for run in runs_data)
    
    if debug:
        print(f"[DEBUG] create_replay_plan: Creating plan with {len(runs_data)} runs, {total_steps} total steps")
        print(f"[DEBUG]   Speed multiplier: {speed_multiplier}")
    
    # Open run once at the beginning - this treats all runs as one continuous sequence
    run_metadata = {
        'plan_name': 'replay_optimization',
        'num_runs': len(runs_data),
        'total_events': total_steps,
    }
    yield from open_run(md=run_metadata)
    
    if debug:
        print(f"[DEBUG] Run opened for all {len(runs_data)} runs")
    
    global_step = 0
    
    for run_idx, run_data in enumerate(runs_data):
        if debug:
            print(f"[DEBUG] Processing run {run_idx+1}/{len(runs_data)} (UID: {run_data['uid']})")
            print(f"[DEBUG]   Motors controlled: {run_data['motors_controlled']}")
            print(f"[DEBUG]   Number of events: {len(run_data['images'])}")
        
        images = run_data['images']
        timestamps = run_data['timestamps']
        motor_positions = run_data['motor_positions']
        motors_controlled = run_data['motors_controlled']
        
        # Calculate time deltas for this run
        if len(timestamps) > 1:
            time_deltas = np.diff(timestamps, prepend=timestamps[0])
            time_deltas = time_deltas / speed_multiplier
        else:
            time_deltas = np.array([0.5 / speed_multiplier])
        
        for event_idx in range(len(images)):
            if debug and (event_idx == 0 or event_idx % 10 == 0 or event_idx == len(images) - 1):
                print(f"[DEBUG]   Run {run_idx+1}, Event {event_idx+1}/{len(images)} (Global step {global_step+1})")
            
            # Set detector index to current global step (images are flattened across all runs)
            # We need to use the event index within THIS run, not global_step
            # because each run has its own images array
            # Actually wait - we've flattened all images, so we should use global_step
            # But we need to make sure we're indexing correctly
            
            # Calculate the correct index: sum of images from previous runs + current event index
            images_before_this_run = sum(len(runs_data[i]['images']) for i in range(run_idx))
            detector_idx = images_before_this_run + event_idx
            detector._current_idx = detector_idx
            
            if debug and (event_idx == 0 or event_idx % 10 == 0):
                print(f"[DEBUG]     Event idx={event_idx}, Global step={global_step}")
                print(f"[DEBUG]     Images before this run={images_before_this_run}, detector_idx={detector_idx}")
                print(f"[DEBUG]     Detector image array length={len(detector.images)}")
                if detector_idx < len(detector.images):
                    img = detector.images[detector_idx]
                    img_hash = hash(img.tobytes()[:1000])  # Hash first 1000 bytes for speed
                    img_sum = img.sum()
                    print(f"[DEBUG]     Image at idx {detector_idx}: hash={img_hash}, sum={img_sum:.2e}")
                else:
                    print(f"[DEBUG]     WARNING: detector_idx {detector_idx} >= array length {len(detector.images)}")
            
            # Build list of motors to move (only those controlled in this run)
            motors_to_move = []
            motor_positions_to_set = []
            
            for motor_key in motors_controlled:
                motor_short_name = motor_map[motor_key]
                if motors[motor_short_name] is not None:
                    # Advance motor to current step
                    motors[motor_short_name]._current_idx = global_step
                    motors_to_move.append(motors[motor_short_name])
                    motor_positions_to_set.append(motor_positions[motor_key][event_idx])
            
            # Move only the motors that were controlled in this run
            if motors_to_move:
                if debug and (event_idx == 0 or event_idx % 10 == 0):
                    motor_info = ", ".join([f"{m.name}={pos:.3f}" for m, pos in zip(motors_to_move, motor_positions_to_set)])
                    print(f"[DEBUG]     Moving motors: {motor_info}")
                
                # Use bps.mv with variable arguments
                yield from bps.mv(*[item for pair in zip(motors_to_move, motor_positions_to_set) for item in pair])
            
            # Build list of all devices to read (motors that were moved + detector)
            devices_to_read = [detector]
            
            # Trigger and read all devices together - this emits an event document
            yield from trigger_and_read(devices_to_read)
            
            # Sleep to maintain timing
            if event_idx < len(time_deltas):
                sleep_time = max(0.01, time_deltas[event_idx])
                if debug and (event_idx == 0 or event_idx % 10 == 0):
                    print(f"[DEBUG]     Sleeping for {sleep_time:.3f}s")
                yield from bps.sleep(sleep_time)
            
            global_step += 1
    
    # Close run once at the very end
    yield from close_run()
    
    if debug:
        print(f"[DEBUG] Run closed - plan execution complete!")


def replay_optimization_runs(uids, speed_multiplier=1.0, tiled_client=None, RE=None, debug=False):
    """
    Replay optimization runs from tiled Run UIDs.
    
    Parameters
    ----------
    uids : list of str
        List of Run UIDs to replay
    speed_multiplier : float, optional
        Speed multiplier for replay (1.0 = real-time, 2.0 = 2x speed)
    tiled_client : tiled client, optional
        Tiled client instance. If None, uses lix_client
    RE : RunEngine, optional
        Bluesky RunEngine instance. If None, expects RE to be available globally
    debug : bool, optional
        Enable debug print statements throughout execution
    
    Returns
    -------
    tuple
        (motors dict, detector, visualizer, plan) for inspection
    """
    if tiled_client is None:
        tiled_client = lix_client
    
    print(f"Extracting data from {len(uids)} runs...")
    runs_data = extract_run_data(uids, tiled_client, debug=debug)
    
    total_events = sum(len(run['images']) for run in runs_data)
    print(f"Found {total_events} total events across {len(runs_data)} runs")
    
    if debug:
        print(f"[DEBUG] Data summary:")
        for idx, run_data in enumerate(runs_data):
            print(f"[DEBUG]   Run {idx+1}: {len(run_data['images'])} events, motors={run_data['motors_controlled']}")
    
    print("Creating mock devices...")
    
    # Collect all motor positions across all runs to create devices
    all_motor_positions = {'crl_x1': [], 'crl_x2': [], 'crl_y1': [], 'crl_y2': []}
    all_timestamps = []
    all_images = []
    
    for run_data in runs_data:
        for motor_key in run_data['motor_positions']:
            all_motor_positions[motor_key].extend(run_data['motor_positions'][motor_key])
        all_timestamps.extend(run_data['timestamps'].tolist())
        all_images.extend(run_data['images'])
    
    # Create mock motors - only for motors that appear in at least one run
    motors = {}
    motor_map = {
        'crl_x1': 'x1',
        'crl_x2': 'x2',
        'crl_y1': 'y1',
        'crl_y2': 'y2'
    }
    
    for motor_key, motor_short_name in motor_map.items():
        if len(all_motor_positions[motor_key]) > 0:
            motors[motor_short_name] = ReplayMotor(
                motor_key,
                all_motor_positions[motor_key],
                all_timestamps,
                debug=debug
            )
            if debug:
                print(f"[DEBUG] Created motor {motor_key} ({motor_short_name}) with {len(all_motor_positions[motor_key])} positions")
        else:
            motors[motor_short_name] = None
            if debug:
                print(f"[DEBUG] Skipping motor {motor_key} ({motor_short_name}) - not in any runs")
    
    # Create mock detector with all images
    detector = ReplayDetector('camSF', np.array(all_images), np.array(all_timestamps), debug=debug)
    
    # Create visualizer
    print("Setting up visualization...")
    visualizer = ReplayVisualizer('camSF', debug=debug)
    
    # Create replay plan
    print("Creating replay plan...")
    plan = create_replay_plan(motors, detector, runs_data, speed_multiplier, debug=debug)
    
    # Subscribe visualizer to RunEngine if provided
    if RE is not None:
        RE.subscribe(visualizer)
        print("Visualizer subscribed to RunEngine.")
        print("Execute with: RE(plan)")
    else:
        print("Ready to replay. Subscribe visualizer and execute:")
        print("  RE.subscribe(visualizer)")
        print("  RE(plan)")
    
    if debug:
        print(f"[DEBUG] replay_optimization_runs complete!")
        print(f"[DEBUG]   Motors: {list(motors.keys())}")
        print(f"[DEBUG]   Detector: {detector.name}")
        print(f"[DEBUG]   Visualizer: {visualizer.detector_name}")
    
    return motors, detector, visualizer, plan


def check_duplicate_images(uids, tiled_client=None, debug=False):
    """
    Check for duplicate images across runs.
    
    Parameters
    ----------
    uids : list of str
        List of Run UIDs to check
    tiled_client : tiled client, optional
        Tiled client instance. If None, uses lix_client
    debug : bool, optional
        Enable debug print statements
    
    Returns
    -------
    dict
        Dictionary with analysis results including:
        - 'image_hashes': dict mapping (run_idx, event_idx) to image hash
        - 'duplicate_groups': list of groups of (run_idx, event_idx) that have identical images
        - 'unique_images': number of unique images found
        - 'total_images': total number of images
    """
    if tiled_client is None:
        tiled_client = lix_client
    
    print(f"Checking for duplicate images across {len(uids)} runs...")
    
    image_hashes = {}  # (run_idx, event_idx) -> hash
    image_data = {}  # (run_idx, event_idx) -> (image, intensity)
    
    for run_idx, uid in enumerate(uids):
        try:
            run = tiled_client[uid]
            primary_data = run["primary/data"]
            
            # Try to get images
            try:
                images = primary_data['camSF_image'].read().squeeze()
            except KeyError:
                if debug:
                    print(f"[DEBUG] Run {run_idx+1} ({uid}): No camSF_image found")
                continue
            
            # Handle different shapes - leading dimension is events
            if len(images.shape) == 2:
                # Single image (height, width) - this is event 0
                images_list = [images.copy()]  # Make a copy!
            elif len(images.shape) == 3:
                # Multiple images (n_events, height, width)
                images_list = [images[i].copy() for i in range(images.shape[0])]  # Make copies!
            else:
                if debug:
                    print(f"[DEBUG] Run {run_idx+1} ({uid}): Unexpected shape {images.shape}")
                continue
            
            for event_idx, img in enumerate(images_list):
                # Calculate hash of image
                img_bytes = img.tobytes()
                img_hash = hash(img_bytes)
                img_sum = img.sum()
                intensity = intensity_metric(img)
                
                image_hashes[(run_idx, event_idx)] = img_hash
                image_data[(run_idx, event_idx)] = (img, intensity)  # img is already a copy
                
                if debug:
                    print(f"[DEBUG] Run {run_idx+1}, Event {event_idx}: hash={img_hash}, sum={img_sum:.2e}, intensity={intensity:.2f}")
        
        except Exception as e:
            print(f"Error processing run {run_idx+1} ({uid}): {e}")
            if debug:
                import traceback
                traceback.print_exc()
            continue
    
    # Find duplicates
    hash_to_locations = {}
    for (run_idx, event_idx), img_hash in image_hashes.items():
        if img_hash not in hash_to_locations:
            hash_to_locations[img_hash] = []
        hash_to_locations[img_hash].append((run_idx, event_idx))
    
    duplicate_groups = [locs for locs in hash_to_locations.values() if len(locs) > 1]
    unique_images = len(hash_to_locations)
    total_images = len(image_hashes)
    
    print(f"\n=== Duplicate Image Analysis ===")
    print(f"Total images: {total_images}")
    print(f"Unique images: {unique_images}")
    print(f"Duplicate groups: {len(duplicate_groups)}")
    
    if duplicate_groups:
        print(f"\nFound {len(duplicate_groups)} groups of duplicate images:")
        for group_idx, group in enumerate(duplicate_groups):
            print(f"\n  Group {group_idx+1} ({len(group)} duplicates):")
            for run_idx, event_idx in group:
                img, intensity = image_data[(run_idx, event_idx)]
                print(f"    Run {run_idx+1} (UID: {uids[run_idx][:8]}...), Event {event_idx}: intensity={intensity:.2f}, sum={img.sum():.2e}")
    else:
        print("\nNo duplicate images found!")
    
    # Check for runs with same intensity but different images
    intensity_to_locations = {}
    for (run_idx, event_idx), (img, intensity) in image_data.items():
        intensity_key = round(intensity, 2)  # Round to 2 decimal places
        if intensity_key not in intensity_to_locations:
            intensity_to_locations[intensity_key] = []
        intensity_to_locations[intensity_key].append((run_idx, event_idx, img))
    
    same_intensity_groups = [(intensity, locs) for intensity, locs in intensity_to_locations.items() if len(locs) > 1]
    
    if same_intensity_groups:
        print(f"\n=== Runs with Same Intensity (but may have different images) ===")
        for intensity, locs in sorted(same_intensity_groups, key=lambda x: len(x[1]), reverse=True)[:10]:
            print(f"\n  Intensity {intensity:.2f} appears in {len(locs)} images:")
            # Check if they're actually the same image
            hashes_in_group = [hash(img.tobytes()) for _, _, img in locs]
            if len(set(hashes_in_group)) == 1:
                print(f"    → All {len(locs)} images are IDENTICAL (same hash)")
            else:
                print(f"    → Images are DIFFERENT (different hashes)")
                for run_idx, event_idx, img in locs[:5]:  # Show first 5
                    print(f"      Run {run_idx+1}, Event {event_idx}: hash={hash(img.tobytes())}")
    
    return {
        'image_hashes': image_hashes,
        'duplicate_groups': duplicate_groups,
        'unique_images': unique_images,
        'total_images': total_images,
        'image_data': image_data
    }


if __name__ == "__main__":
    # Example usage
    print("Optimization Replay Script")
    print("=" * 50)
    print("\nUsage:")
    print("  from replay_optimization import replay_optimization_runs")
    print("  motors, detector, visualizer, plan = replay_optimization_runs(['uid1', 'uid2', ...])")
    print("  RE(plan)")
    print("\nOr in IPython:")
    print("  %run replay_optimization.py")
    print("  # Then call replay_optimization_runs with your UIDs")

