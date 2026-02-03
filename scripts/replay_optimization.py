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
import bluesky.preprocessors as bpp
from tiled.client import from_uri, from_profile
from tiled.server import SimpleTiledServer
import cv2
from datetime import datetime
try:
    from matplotlib.animation import FFMpegWriter
    HAS_VIDEO = True
except ImportError:
    HAS_VIDEO = False

# GP model imports for visualization
try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
    HAS_GP = True
except ImportError:
    HAS_GP = False
    print("Warning: scikit-learn not available. GP visualization disabled.")


lix_client = from_uri("https://tiled.nsls2.bnl.gov/")["lix"]["raw"]

# Import intensity_metric from 60-utils
# We'll copy it here to avoid import issues
def process_image_for_metric(image, background=None, threshold_factor=0.4, edge_crop=0, return_processed=False):
    """
    Process image for intensity metric calculation.
    
    Parameters
    ----------
    image : ndarray
        Input image
    background : ndarray, optional
        Background image to subtract
    threshold_factor : float
        Threshold factor (0-1) for intensity thresholding
    edge_crop : int
        Number of pixels to crop from edges
    return_processed : bool
        If True, return (intensity, processed_image), else just intensity
    
    Returns
    -------
    float or tuple
        If return_processed=False: total intensity
        If return_processed=True: (total_intensity, processed_image)
    """
    # Convert to grayscale
    image = image.squeeze()
    if len(image.shape) == 3 and image.shape[0] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # crop the image to remove noise around the edges
    gray = gray[200:500, 600:1000]

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
        if return_processed:
            return float('inf'), corrected
        return float('inf')
        
    thresh_value = threshold_factor * max_intensity
    _, thresh = cv2.threshold(corrected, thresh_value, 255, cv2.THRESH_TOZERO)
    
    # Total integrated intensity
    total_intensity = np.sum(thresh)
    
    if return_processed:
        return total_intensity, thresh
    return total_intensity


def intensity_metric(image, background=None, threshold_factor=0.4, edge_crop=0):
    """Calculate beam intensity from image."""
    return process_image_for_metric(image, background, threshold_factor, edge_crop, return_processed=False)


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
    
    def reset(self):
        """Reset to initial position."""
        self._current_idx = 0
        if len(self.positions) > 0:
            self._position.put(self.positions[0])


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
    
    def reset(self):
        """Reset to initial image."""
        self._current_idx = 0
        if self.debug:
            print(f"[DEBUG] {self.name}.reset() -> idx=0")


class ReplayVisualizer(CallbackBase):
    """Visualization callback for replay."""
    
    def __init__(self, detector_name="camSF", debug=False, record_video=False, video_filename=None, fps=10):
        super().__init__()
        self.detector_name = detector_name
        self.debug = debug
        self.record_video = record_video
        self.fps = fps
        
        # Generate video filename if not provided
        if record_video and video_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_filename = f"replay_optimization_{timestamp}.mp4"
        self.video_filename = video_filename
        
        # Initialize video writer if recording
        self.video_writer = None
        if record_video:
            if not HAS_VIDEO:
                print("Warning: matplotlib.animation.FFMpegWriter not available. Video recording disabled.")
                print("  Install ffmpeg to enable video recording.")
                self.record_video = False
            else:
                print(f"Video recording enabled: {video_filename} (fps={fps})")
                # Switch to Agg backend for flicker-free video recording
                # plt.switch_backend('Agg')
                # print("  Using Agg backend for video recording")
        
        # Create figure with grid: intensity plot, image, and single row of 2 motor pair plots
        # Tighter layout for PowerPoint embedding - less horizontal stretch
        self.fig = plt.figure(figsize=(12, 10))
        # Main gridspec: only 2 rows (intensity plot + image plots), no unused row
        gs = self.fig.add_gridspec(2, 2, hspace=0.15, wspace=0.1, 
                                    left=0.05, right=0.98, top=0.95, bottom=0.30)
        
        # Top row: intensity plot (spans 2 columns)
        self.ax1 = self.fig.add_subplot(gs[0, :])
        self.ax1.set_xlabel("Step")
        self.ax1.set_ylabel("Beam Intensity (×10⁶)")
        self.ax1.set_title("Objective Metric")
        self.ax1.grid(True)
        self.intensity_data = []
        self.step_data = []
        self.line, = self.ax1.plot([], [], 'b-o', markersize=4)
        
        # Middle left: detector image
        self.ax2 = self.fig.add_subplot(gs[1, 0])
        self.ax2.set_title("Detector Image")
        self.ax2.set_xlabel("X (pixels)")
        self.ax2.set_ylabel("Y (pixels)")
        self.im = None
        
        # Middle right: processed image (cropped, blurred, thresholded)
        self.ax_placeholder = self.fig.add_subplot(gs[1, 1])
        self.ax_placeholder.set_title("Processed Image")
        self.ax_placeholder.set_xlabel("X (pixels)")
        self.ax_placeholder.set_ylabel("Y (pixels)")
        self.im_processed = None
        
        # Bottom row: single row of 2 plots for motor pair scatter plots
        # Only show (x1,x2) and (y1,y2) pairs
        # Positioned with gap below the image plots (top=0.24 to avoid title/axis overlap)
        gs_bottom = self.fig.add_gridspec(1, 2, left=0.05, right=0.98, bottom=0.05, top=0.24, hspace=0.1, wspace=0.1)
        self.ax_pairs = {
            ('x1', 'x2'): self.fig.add_subplot(gs_bottom[0, 0]),
            ('y1', 'y2'): self.fig.add_subplot(gs_bottom[0, 1]),
        }
        
        # Track motor positions and scatter plots
        self.motor_positions = {'x1': [], 'x2': [], 'y1': [], 'y2': []}
        self.motor_pair_data = {}  # (motor1, motor2) -> (x_data, y_data, intensity_data)
        self.scatter_plots = {}  # (motor1, motor2) -> scatter plot object
        self.current_run_motors_controlled = set()  # Track which motors are active in current run
        self.last_motor_positions = {}  # Track last positions to detect which motors are actually changing
        
        # Motor name mapping
        self.motor_map = {
            'crl_x1': 'x1',
            'crl_x2': 'x2',
            'crl_y1': 'y1',
            'crl_y2': 'y2'
        }
        
        # GP model configuration and storage
        self.gp_models = {}  # (motor1, motor2) -> fitted GP model
        self.gp_contourf = {}  # (motor1, motor2) -> filled contour plot object
        self.gp_contour_lines = {}  # (motor1, motor2) -> contour line objects
        self.gp_update_interval = 3  # Refit GP every N events
        self.min_points_for_gp = 6  # Minimum data points before fitting GP
        
        # Use subplots_adjust for precise control with adequate padding
        plt.subplots_adjust(left=0.05, right=0.98, top=0.95, bottom=0.05, hspace=0.15, wspace=0.1)
        
        # Only enable interactive mode when NOT recording video
        # Interactive mode causes flickering during video capture
        if not self.record_video:
            plt.ion()
            plt.show(block=False)
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()
        else:
            # For video recording, use non-interactive mode
            plt.ioff()
            self.fig.canvas.draw()
        
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer initialized for detector '{detector_name}'")
            print(f"[DEBUG]   Figure created: {self.fig}")
            print(f"[DEBUG]   Main axes: {self.ax1}, {self.ax2}")
            print(f"[DEBUG]   Motor pair axes: {list(self.ax_pairs.keys())}")
    
    def _fit_gp(self, pair_key, x_data, y_data, intensity_data):
        """
        Fit a 2D Gaussian Process model to motor positions and intensity.
        
        Parameters
        ----------
        pair_key : tuple
            (motor1, motor2) tuple identifying the motor pair
        x_data : list
            Motor 1 positions
        y_data : list
            Motor 2 positions
        intensity_data : array
            Intensity values corresponding to positions
        
        Returns
        -------
        GaussianProcessRegressor or None
            Fitted GP model, or None if fitting fails
        """
        if not HAS_GP:
            return None
        
        if len(x_data) < self.min_points_for_gp:
            return None
        
        try:
            # Prepare training data (intensity_data is already aligned with x_data, y_data)
            X_train = np.column_stack([x_data, y_data])
            y_train = np.array(intensity_data)
            
            # Define kernel: RBF with automatic length scale + constant + noise
            kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(length_scale=[0.1, 0.1], length_scale_bounds=(1e-3, 1e1)) + WhiteKernel(noise_level=1e-5, noise_level_bounds=(1e-10, 1e1))
            
            # Fit GP with normalization for numerical stability
            gp = GaussianProcessRegressor(
                kernel=kernel,
                n_restarts_optimizer=2,
                normalize_y=True,
                alpha=1e-6  # Small regularization for numerical stability
            )
            gp.fit(X_train, y_train)
            
            self.gp_models[pair_key] = gp
            
            if self.debug:
                print(f"[DEBUG] GP fitted for {pair_key} with {len(x_data)} points")
            
            return gp
            
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] GP fit failed for {pair_key}: {e}")
            return None
    
    def _plot_gp_surface(self, pair_key, ax, gp_model, x_data, y_data, intensity_data):
        """
        Plot the GP prediction surface with filled contours and contour lines.
        
        Parameters
        ----------
        pair_key : tuple
            (motor1, motor2) tuple identifying the motor pair
        ax : matplotlib.axes.Axes
            Axes to plot on
        gp_model : GaussianProcessRegressor
            Fitted GP model
        x_data : list
            Motor 1 positions
        y_data : list
            Motor 2 positions
        intensity_data : array
            Intensity values
        """
        if gp_model is None or len(x_data) < self.min_points_for_gp:
            return
        
        try:
            # Create prediction grid with 10% padding
            x_min, x_max = min(x_data), max(x_data)
            y_min, y_max = min(y_data), max(y_data)
            x_range = x_max - x_min if x_max > x_min else 0.1
            y_range = y_max - y_min if y_max > y_min else 0.1
            x_pad = x_range * 0.1
            y_pad = y_range * 0.1
            
            x_grid = np.linspace(x_min - x_pad, x_max + x_pad, 40)
            y_grid = np.linspace(y_min - y_pad, y_max + y_pad, 40)
            X_grid, Y_grid = np.meshgrid(x_grid, y_grid)
            X_pred = np.column_stack([X_grid.ravel(), Y_grid.ravel()])
            
            # Predict mean (no need for std since we removed uncertainty viz)
            y_pred = gp_model.predict(X_pred, return_std=False)
            Z_pred = y_pred.reshape(X_grid.shape)
            
            # Remove old contours if they exist (compatible with newer matplotlib)
            if pair_key in self.gp_contourf and self.gp_contourf[pair_key] is not None:
                try:
                    # Try newer matplotlib API first (3.8+)
                    self.gp_contourf[pair_key].remove()
                except (AttributeError, ValueError):
                    # Fall back to older API
                    try:
                        for coll in self.gp_contourf[pair_key].collections:
                            coll.remove()
                    except (AttributeError, ValueError):
                        pass
            
            if pair_key in self.gp_contour_lines and self.gp_contour_lines[pair_key] is not None:
                try:
                    # Try newer matplotlib API first (3.8+)
                    self.gp_contour_lines[pair_key].remove()
                except (AttributeError, ValueError):
                    # Fall back to older API
                    try:
                        for coll in self.gp_contour_lines[pair_key].collections:
                            coll.remove()
                    except (AttributeError, ValueError):
                        pass
                # Remove clabels if any
                for text in ax.texts[:]:
                    try:
                        text.remove()
                    except ValueError:
                        pass
            
            # Plot filled contours (zorder=0, behind everything)
            # Use fixed colorbar limits matching scatter plots: 9500-70000
            levels = np.linspace(9500, 70000, 20)
            contourf = ax.contourf(X_grid, Y_grid, Z_pred, levels=levels, cmap='viridis', 
                                   alpha=0.4, zorder=0, extend='both')
            self.gp_contourf[pair_key] = contourf
            
            # Plot contour lines (zorder=2)
            contour_lines = ax.contour(X_grid, Y_grid, Z_pred, levels=levels[::4], 
                                        colors='white', linewidths=0.5, alpha=0.7, zorder=2)
            # Add labels to contour lines
            ax.clabel(contour_lines, inline=True, fontsize=6, fmt='%.0f')
            self.gp_contour_lines[pair_key] = contour_lines
            
            if self.debug:
                print(f"[DEBUG] GP surface plotted for {pair_key}")
                print(f"[DEBUG]   Prediction range: [{Z_pred.min():.0f}, {Z_pred.max():.0f}]")
                
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] GP surface plot failed for {pair_key}: {e}")
                import traceback
                traceback.print_exc()
    
    def start(self, doc):
        """Initialize on run start."""
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer.start() called")
            print(f"[DEBUG]   Run UID: {doc.get('uid', 'N/A')}")
            print(f"[DEBUG]   Detectors: {doc.get('detectors', [])}")
        
        # Reset motor tracking
        self.current_run_motors_controlled = set()
        self.last_motor_positions = {}
        
        # Initialize video writer if recording
        if self.record_video and HAS_VIDEO and self.video_writer is None:
            self.video_writer = FFMpegWriter(fps=self.fps, 
                                            metadata=dict(artist='ReplayOptimization', 
                                                         title='Optimization Replay'))
            self.video_writer.setup(self.fig, self.video_filename, dpi=100)
            if self.debug:
                print(f"[DEBUG] Video writer initialized: {self.video_filename}")
        
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
        
        # Clear processed image plot
        self.ax_placeholder.clear()
        self.ax_placeholder.set_title("Processed Image")
        self.ax_placeholder.set_xlabel("X (pixels)")
        self.ax_placeholder.set_ylabel("Y (pixels)")
        self.im_processed = None
        
        # Clear motor data
        self.motor_positions = {'x1': [], 'x2': [], 'y1': [], 'y2': []}
        self.motor_pair_data = {}
        
        # Clear scatter plots
        for ax in self.ax_pairs.values():
            ax.clear()
        for scatter in self.scatter_plots.values():
            try:
                scatter.remove()
            except ValueError:
                pass
        self.scatter_plots.clear()
        
        # Clear GP-related state
        self.gp_models.clear()
        
        # Remove GP contour visualizations (compatible with newer matplotlib)
        for contourf in self.gp_contourf.values():
            if contourf is not None:
                try:
                    contourf.remove()
                except (AttributeError, ValueError):
                    try:
                        for coll in contourf.collections:
                            coll.remove()
                    except (AttributeError, ValueError):
                        pass
        self.gp_contourf.clear()
        
        for contour_lines in self.gp_contour_lines.values():
            if contour_lines is not None:
                try:
                    contour_lines.remove()
                except (AttributeError, ValueError):
                    try:
                        for coll in contour_lines.collections:
                            coll.remove()
                    except (AttributeError, ValueError):
                        pass
        self.gp_contour_lines.clear()
        
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
            
            # Calculate intensity metric and get processed image
            # Use the exact same image for both metric calculation and visualization
            # Process the image in its original orientation (no transpose needed)
            intensity, processed_image = process_image_for_metric(image, return_processed=True)
            intensity_millions = intensity
            
            if self.debug:
                print(f"[DEBUG]   Calculated intensity: {intensity_millions:.2f} (×10⁶)")
                print(f"[DEBUG]   Original image shape: {image.shape}")
                print(f"[DEBUG]   Processed image shape: {processed_image.shape}")
            
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
            
            # Update processed image display in placeholder
            # Display the EXACT processed image that was used for the metric calculation
            processed_image_display = processed_image
            
            if self.im_processed is None:
                # Create initial processed image display
                # Fixed colorbar limits for Processed Image (Row 2 Col 2): min=0, max=90
                self.im_processed = self.ax_placeholder.imshow(processed_image_display, cmap='hot', aspect='auto', 
                                                              interpolation='nearest', vmin=0, vmax=90)
                self.ax_placeholder.set_xlim(-0.5, processed_image_display.shape[1] - 0.5)
                self.ax_placeholder.set_ylim(processed_image_display.shape[0] - 0.5, -0.5)  # Flip y-axis
                self.fig.colorbar(self.im_processed, ax=self.ax_placeholder, label='Intensity')
            else:
                # Update processed image
                self.im_processed.set_data(processed_image_display)
                # Fixed colorbar limits for Processed Image (Row 2 Col 2): min=0, max=90
                self.im_processed.set_clim(vmin=0, vmax=90)
            
            # Extract motor positions from event data (do this before image processing)
            current_motor_positions = {}
            for motor_key, motor_short in self.motor_map.items():
                motor_field = f"{motor_key}_position"
                if motor_field in data:
                    motor_data = data[motor_field]
                    if isinstance(motor_data, dict):
                        pos = motor_data.get('value', motor_data)
                    else:
                        pos = motor_data
                    try:
                        pos_value = float(pos)
                        current_motor_positions[motor_short] = pos_value
                        self.motor_positions[motor_short].append(pos_value)
                        
                        # Detect which motors are actually changing (indicating they're being controlled)
                        if motor_short in self.last_motor_positions:
                            if abs(pos_value - self.last_motor_positions[motor_short]) > 1e-4:
                                # Motor position changed, it's being controlled
                                self.current_run_motors_controlled.add(motor_short)
                        else:
                            # First time seeing this motor, assume it's controlled if it has a value
                            self.current_run_motors_controlled.add(motor_short)
                        
                        self.last_motor_positions[motor_short] = pos_value
                    except (ValueError, TypeError):
                        if self.debug:
                            print(f"[DEBUG]   Could not convert motor {motor_key} position: {pos}")
            
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
                
                # Fixed colorbar limits for Detector Image (Row 2 Col 1)
                img_min = 0
                img_max = 30
                
                self.im = self.ax2.imshow(image, cmap='turbo', aspect='auto', interpolation='nearest', 
                                         vmin=img_min, vmax=img_max)
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
                # Fixed colorbar limits for Detector Image (Row 2 Col 1)
                self.im.set_clim(vmin=0, vmax=30)
            
            # Update scatter plots for motor pairs (use motor positions extracted above)
            # Only plot pairs where BOTH motors were actually controlled in the current run
            if len(current_motor_positions) >= 2 and len(self.current_run_motors_controlled) >= 2:
                # Get all active motors that were actually controlled in this run
                active_motors = sorted([m for m in current_motor_positions.keys() 
                                      if m in self.current_run_motors_controlled])
                
                # Create pairs and update scatter plots (only for motors that were both controlled)
                for i, motor1 in enumerate(active_motors):
                    for motor2 in active_motors[i+1:]:
                        # Both motors must be in the controlled set
                        if motor1 not in self.current_run_motors_controlled or \
                           motor2 not in self.current_run_motors_controlled:
                            continue
                        
                        pair = (motor1, motor2)
                        pair_reversed = (motor2, motor1)
                        
                        # Use canonical ordering (alphabetical)
                        if pair not in self.motor_pair_data and pair_reversed not in self.motor_pair_data:
                            self.motor_pair_data[pair] = ([], [], [])  # (x_data, y_data, intensity_data)
                        
                        # Get the canonical pair key
                        pair_key = pair if pair in self.motor_pair_data else pair_reversed
                        
                        # Check if this point is different from the last one (avoid duplicates)
                        should_add_point = True
                        if pair_key in self.motor_pair_data and len(self.motor_pair_data[pair_key][0]) > 0:
                            # Check if this is the same as the last point
                            last_x = self.motor_pair_data[pair_key][0][-1]
                            last_y = self.motor_pair_data[pair_key][1][-1]
                            new_x = current_motor_positions[motor1] if pair_key == pair else current_motor_positions[motor2]
                            new_y = current_motor_positions[motor2] if pair_key == pair else current_motor_positions[motor1]
                            
                            # Only add if position changed (with small tolerance for floating point)
                            if abs(new_x - last_x) < 1e-6 and abs(new_y - last_y) < 1e-6:
                                should_add_point = False
                        
                        # Add data point only if it's new (including the corresponding intensity)
                        if should_add_point:
                            current_intensity = intensity_millions  # Use the intensity from this event
                            if pair_key == pair:
                                self.motor_pair_data[pair_key][0].append(current_motor_positions[motor1])
                                self.motor_pair_data[pair_key][1].append(current_motor_positions[motor2])
                            else:
                                self.motor_pair_data[pair_key][0].append(current_motor_positions[motor2])
                                self.motor_pair_data[pair_key][1].append(current_motor_positions[motor1])
                            self.motor_pair_data[pair_key][2].append(current_intensity)
                        
                        # Update or create scatter plot
                        if pair_key in self.ax_pairs:
                            ax = self.ax_pairs[pair_key]
                            x_data, y_data, point_intensities = self.motor_pair_data[pair_key]
                            
                            if self.debug and len(x_data) % 10 == 0:
                                print(f"[DEBUG]   Updating scatter plot {pair_key}: {len(x_data)} points")
                                if len(x_data) > 0:
                                    print(f"[DEBUG]     x range: [{min(x_data):.3f}, {max(x_data):.3f}]")
                                    print(f"[DEBUG]     y range: [{min(y_data):.3f}, {max(y_data):.3f}]")
                            
                            if len(x_data) == 0:
                                # Skip if no data yet
                                continue
                            
                            if pair_key in self.scatter_plots:
                                # Update existing scatter plot
                                scatter = self.scatter_plots[pair_key]
                                scatter.set_offsets(np.column_stack([x_data, y_data]))
                                # Update colors using stored intensity values (properly aligned with positions)
                                # Fixed colorbar limits for scatter plots (Row 3): min=9500, max=70000
                                if len(point_intensities) == len(x_data):
                                    scatter.set_array(np.array(point_intensities))
                                    scatter.set_clim(vmin=9500, vmax=70000)
                            else:
                                # Create new scatter plot
                                # Fixed colorbar limits for scatter plots (Row 3): min=9500, max=70000
                                if len(point_intensities) == len(x_data) and len(x_data) > 0:
                                    scatter = ax.scatter(x_data, y_data, c=point_intensities, cmap='viridis', 
                                                         s=20, alpha=0.6, edgecolors='black', linewidths=0.5,
                                                         vmin=9500, vmax=70000)
                                    # Add colorbar (only once)
                                    plt.colorbar(scatter, ax=ax, label='Intensity')
                                else:
                                    scatter = ax.scatter(x_data, y_data, c='blue', 
                                                         s=20, alpha=0.6, edgecolors='black', linewidths=0.5)
                                self.scatter_plots[pair_key] = scatter
                                ax.set_xlabel(f"{motor1} position")
                                ax.set_ylabel(f"{motor2} position")
                                ax.set_title(f"{motor1} vs {motor2}")
                                ax.grid(True, alpha=0.3)
                            
                            # Update axis limits manually (relim/autoscale doesn't work well with scatter)
                            if len(x_data) > 0:
                                x_min, x_max = min(x_data), max(x_data)
                                y_min, y_max = min(y_data), max(y_data)
                                # Add small margin
                                x_range = x_max - x_min
                                y_range = y_max - y_min
                                x_margin = x_range * 0.05 if x_range > 0 else abs(x_min) * 0.05 if x_min != 0 else 0.1
                                y_margin = y_range * 0.05 if y_range > 0 else abs(y_min) * 0.05 if y_min != 0 else 0.1
                                ax.set_xlim(x_min - x_margin, x_max + x_margin)
                                ax.set_ylim(y_min - y_margin, y_max + y_margin)
                            
                            # Update GP model periodically
                            if HAS_GP and len(x_data) >= self.min_points_for_gp:
                                if len(self.step_data) % self.gp_update_interval == 0:
                                    # Use properly aligned intensity data for GP fitting
                                    gp_model = self._fit_gp(pair_key, x_data, y_data, point_intensities)
                                    if gp_model is not None:
                                        self._plot_gp_surface(pair_key, ax, gp_model, x_data, y_data, point_intensities)
                                    
                                    # Update scatter plot zorder to be above GP surface
                                    if pair_key in self.scatter_plots:
                                        self.scatter_plots[pair_key].set_zorder(3)
            
            # Force redraw and capture frame
            try:
                if self.record_video and self.video_writer is not None:
                    # For video recording, ensure full render before capture
                    # 1. Draw all artists to the canvas
                    self.fig.canvas.draw()
                    # 2. Force the renderer to complete all pending operations
                    #    This ensures complex elements like contours are fully rendered
                    _ = self.fig.canvas.get_renderer()
                    # 3. Process any pending events
                    self.fig.canvas.flush_events()
                    # 4. Small delay to ensure render pipeline completes
                    ttime.sleep(0.02)
                    # 5. Now grab the fully rendered frame
                    self.video_writer.grab_frame()
                else:
                    self.fig.canvas.draw()
                    self.fig.canvas.flush_events()
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG]   Canvas draw error: {e}")
        else:
            if self.debug:
                print(f"[DEBUG]   Image key '{image_key}' not found in event data")
        
        super().event(doc)
    
    def stop(self, doc):
        """Finalize on run stop."""
        if self.debug:
            print(f"[DEBUG] ReplayVisualizer.stop() called")
            print(f"[DEBUG]   Total events processed: {len(self.step_data)}")
        
        # Finish video recording
        if self.record_video and self.video_writer is not None:
            try:
                self.video_writer.finish()
                print(f"Video saved successfully: {self.video_filename}")
            except Exception as e:
                print(f"Error finishing video: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.video_writer = None
        
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


def create_replay_plan(motors, detector, runs_data, speed_multiplier=1.0, debug=False, visualizer_class=None, visualizer_kwargs=None):
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
    visualizer_class : class, optional
        ReplayVisualizer class to instantiate. If None, uses ReplayVisualizer.
    
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
    
    # Create a new visualizer instance for this plan execution
    if visualizer_class is None:
        visualizer_class = ReplayVisualizer
    
    # Use provided kwargs or default
    if visualizer_kwargs is None:
        visualizer_kwargs = {'detector_name': detector.name, 'debug': debug}
    else:
        visualizer_kwargs = dict(visualizer_kwargs)  # Make a copy
        visualizer_kwargs.setdefault('detector_name', detector.name)
        visualizer_kwargs.setdefault('debug', debug)
    
    # Instantiate visualizer with kwargs
    visualizer = visualizer_class(**visualizer_kwargs)
    
    # Define the inner plan body
    def inner_plan():
        # Open run once at the beginning - this treats all runs as one continuous sequence
        # Collect all unique motors_controlled across all runs for initial metadata
        all_motors_controlled = set()
        for run_data in runs_data:
            all_motors_controlled.update(run_data.get('motors_controlled', []))
        
        run_metadata = {
            'plan_name': 'replay_optimization',
            'num_runs': len(runs_data),
            'total_events': total_steps,
            'all_motors_controlled': list(all_motors_controlled),  # For reference
        }
        yield from open_run(md=run_metadata)
        
        if debug:
            print(f"[DEBUG] Run opened for all {len(runs_data)} runs")
        
        # Collect all motors that exist (across all runs) - we need to read all of them
        # to maintain descriptor consistency
        all_motors_to_read = [m for m in motors.values() if m is not None]
        
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
            
            # Convert motor keys to short names for this run
            motors_controlled_short = set()
            for motor_key in motors_controlled:
                if motor_key in motor_map:
                    motors_controlled_short.add(motor_map[motor_key])
            
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
                
                # Build list of all devices to read
                # IMPORTANT: Always read all motors (not just moved ones) to maintain descriptor consistency
                # Bluesky requires that all events read the same devices that were declared in the descriptor
                devices_to_read = all_motors_to_read + [detector]
                
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
    
    # Wrap the plan with subs_wrapper to subscribe the visualizer only for this plan
    return bpp.subs_wrapper(inner_plan(), visualizer)


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
        (motors dict, detector, plan, make_plan) where:
        - motors: dict of ReplayMotor instances
        - detector: ReplayDetector instance
        - plan: initial plan generator (can be used once)
        - make_plan: callable function that creates a new plan each time it's called.
                     Each plan creates a new visualizer instance automatically.
                     Usage: RE(make_plan()) or RE(make_plan(speed_mult=2.0))
                     After reloading the file, RE(make_plan()) will use the updated visualizer class.
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
    
    # Create a reusable plan factory function
    # The visualizer will be created fresh each time make_plan() is called
    def make_plan(speed_mult=None, visualizer_class=None, record_video=False, video_filename=None, fps=10):
        """
        Create a new replay plan. Resets all devices to initial state and creates a new visualizer.
        
        Parameters
        ----------
        speed_mult : float, optional
            Speed multiplier for this replay. If None, uses the original speed_multiplier.
        visualizer_class : class, optional
            ReplayVisualizer class to use. If None, uses ReplayVisualizer from current module.
        record_video : bool, optional
            If True, record the visualization to a video file. Default: False
        video_filename : str, optional
            Filename for the video. If None, auto-generates with timestamp.
        fps : int, optional
            Frames per second for the video. Default: 10
        
        Returns
        -------
        generator
            A new Bluesky plan generator that can be executed with RE(plan)
            The visualizer is automatically subscribed for this plan execution only.
        """
        # Reset all devices to initial state
        for motor in motors.values():
            if motor is not None:
                motor.reset()
        detector.reset()
        
        # Use provided speed_mult or original
        current_speed = speed_mult if speed_mult is not None else speed_multiplier
        
        # Use provided visualizer_class or default to ReplayVisualizer
        if visualizer_class is None:
            visualizer_class = ReplayVisualizer
        
        if debug:
            print(f"[DEBUG] Creating new plan with speed_multiplier={current_speed}")
            print(f"[DEBUG] Using visualizer class: {visualizer_class.__name__}")
            if record_video:
                print(f"[DEBUG] Video recording enabled: {video_filename}")
        
        # Pass video recording parameters to visualizer
        visualizer_kwargs = {
            'record_video': record_video,
            'video_filename': video_filename,
            'fps': fps,
            'detector_name': detector.name,
            'debug': debug
        }
        
        return create_replay_plan(motors, detector, runs_data, current_speed, 
                                 debug=debug, visualizer_class=visualizer_class,
                                 visualizer_kwargs=visualizer_kwargs)
    
    # Create initial plan for backward compatibility
    print("Creating replay plan...")
    plan = make_plan()
    
    print("Ready to replay. Execute with: RE(plan)")
    print("To replay again, use: RE(make_plan()) or RE(make_plan(speed_mult=2.0))")
    print("After reloading the file, use: RE(make_plan()) to get updated visualizer/metric")
    
    if debug:
        print(f"[DEBUG] replay_optimization_runs complete!")
        print(f"[DEBUG]   Motors: {list(motors.keys())}")
        print(f"[DEBUG]   Detector: {detector.name}")
    
    return motors, detector, plan, make_plan


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
    print("  motors, detector, plan, make_plan = replay_optimization_runs(['uid1', 'uid2', ...])")
    print("  RE(plan)  # First replay (visualizer auto-subscribed)")
    print("  RE(make_plan())  # Replay again (no need to re-query Tiled!)")
    print("  RE(make_plan(speed_mult=2.0))  # Replay at 2x speed")
    print("\nAfter modifying intensity_metric or visualizer settings:")
    print("  %run -i scripts/replay_optimization.py  # Reload file")
    print("  RE(make_plan())  # Uses updated visualizer/metric automatically")
    print("\nOr in IPython:")
    print("  %run replay_optimization.py")
    print("  # Then call replay_optimization_runs with your UIDs")

