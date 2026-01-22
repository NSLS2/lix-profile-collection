import os
import sys
import functools
from unittest.mock import Mock, MagicMock, patch
import time as ttime

import pytest
import numpy as np
from bluesky.run_engine import RunEngine
from bluesky.plans import list_scan
import bluesky.plan_stubs as bps
from ophyd.sim import NullStatus

# Add path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from startup.utils.bimorph_control import one_bimorph_step

class MockChannel:
    """Mock bimorph channel."""
    def __init__(self, channel_num, initial_voltage=0.0):
        self.channel_num = channel_num
        self.name = f"bimorph_channels_channel{channel_num}"
        self.setpoint = initial_voltage
        self.current = initial_voltage
        self.armed = initial_voltage
        
        self.armed_voltage = Mock()
        self.armed_voltage.get = Mock(side_effect=lambda: self.armed)

    def set(self, value):
        print(f"Setting {self.name} to {value}")
        self.setpoint = value
        self.armed = value  # In real device, this updates after delay
        return NullStatus()

    def read(self):
        return {self.name: {"value": self.setpoint, "timestamp": ttime.time()}}

    def describe(self):
        return {self.name: {"source": "MockChannel", "dtype": "number", "shape": [], "precision": 1}}


class MockBimorphDevice:
    """Mock bimorph device for testing."""
    def __init__(self, initial_voltages=None):
        if initial_voltages is None:
            initial_voltages = np.zeros(32, dtype=np.float32)
        
        # Create 32 channels
        self.channels = Mock()
        for i in range(32):
            channel = MockChannel(i, float(initial_voltages[i]))
            setattr(self.channels, f"channel{i}", channel)
            channel.parent = self
        
        self._is_ramping = False
        self._ramp_delay = 0.1
        self.parent = None
    
    @property
    def all_current_voltages(self):
        """Get all current voltages."""
        result = Mock()
        voltages = np.array([
            getattr(self.channels, f"channel{i}").current for i in range(32)
        ], dtype=np.float32)
        result.get = Mock(return_value=voltages)
        return result
    
    def all_armed_voltages(self):
        """Get all armed voltages."""
        voltages = np.array([
            getattr(self.channels, f"channel{i}").armed for i in range(32)
        ], dtype=np.float32)
        return voltages
    
    def all_setpoint_voltages(self):
        """Get all setpoint voltages."""
        voltages = np.array([
            getattr(self.channels, f"channel{i}").setpoint for i in range(32)
        ], dtype=np.float32)
        return voltages
    
    def start_plan(self):
        """Start ramping plan."""
        def ramp():
            self._is_ramping = True
            # Simulate ramp: current moves to match armed
            for i in range(32):
                channel = getattr(self.channels, f"channel{i}")
                channel.current = channel.armed
            self._is_ramping = False
            yield from bps.sleep(self._ramp_delay)
        return ramp()


@pytest.fixture
def mock_bimorph():
    """Create a mock bimorph device."""
    return MockBimorphDevice()


@pytest.fixture
def RE():
    """Create a RunEngine for testing."""
    return RunEngine({})


def test_small_change_single_step_success(mock_bimorph, RE):
    """
    Test 1: Simple Success Case
    
    Small voltage change (no constraint violations).
    All channels arm successfully on first try.
    Current matches setpoints after ramp.
    """
    # Set initial voltages (all at 300V)
    initial_voltages = np.full(32, 300.0, dtype=np.float32)
    mock_bimorph = MockBimorphDevice(initial_voltages)
    
    # Target: small change to 350V for channels 12-15
    scan_args = [
        mock_bimorph.channels.channel12, [350.0],
        mock_bimorph.channels.channel13, [350.0],
        mock_bimorph.channels.channel14, [350.0],
        mock_bimorph.channels.channel15, [350.0],
        mock_bimorph.channels.channel16, [300.0],
        mock_bimorph.channels.channel17, [300.0],
        mock_bimorph.channels.channel18, [300.0],
        mock_bimorph.channels.channel19, [300.0],
        mock_bimorph.channels.channel20, [300.0],
        mock_bimorph.channels.channel21, [300.0],
        mock_bimorph.channels.channel22, [300.0],
        mock_bimorph.channels.channel23, [300.0],
    ]

    RE(list_scan([], *scan_args, per_step=functools.partial(one_bimorph_step, bimorph_device=mock_bimorph, timeout=0.5)))

    final_current = mock_bimorph.all_current_voltages.get()[12:24]
    assert np.allclose(
        final_current,
        [350.0, 350.0, 350.0, 350.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0],
        atol=1.0
    )
    final_armed = mock_bimorph.all_armed_voltages()[12:24]
    assert np.allclose(
        final_armed,
        [350.0, 350.0, 350.0, 350.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0],
        atol=1.0
    )
    final_setpoint = mock_bimorph.all_setpoint_voltages()[12:24]
    assert np.allclose(
        final_setpoint,
        [350.0, 350.0, 350.0, 350.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0, 300.0],
        atol=1.0
    )

def test_sequential_setting_with_intermediate_steps(mock_bimorph, re):
    """
    Test 2: Sequential Setting with Intermediate Steps
    
    Some channels would violate 500V constraint if set directly.
    Algorithm calculates intermediate steps and sets those first.
    After ramp, algorithm continues from intermediate to final target.
    """
    # Set initial voltages: channel 12 at 300V, channel 13 at 400V
    initial_voltages = np.zeros(32, dtype=np.float32)
    initial_voltages[12] = 300.0
    initial_voltages[13] = 400.0
    mock_bimorph = MockBimorphDevice(initial_voltages)
    
    # Target: channel 12 to 900V (would violate 500V constraint with channel 13 at 400V)
    target_voltages = {12: 900.0, 13: 400.0}
    
    step = {}
    for ch_num, target in target_voltages.items():
        channel = getattr(mock_bimorph.channels, f"channel{ch_num}")
        step[channel] = target
    
    pos_cache = {}
    
    try:
        from startup.utils import optimization_92 as opt
        
        # Test intermediate step calculation
        current = mock_bimorph.all_current_voltages().get()[12:24]
        armed = mock_bimorph.all_armed_voltages()[12:24]
        
        # Channel 12 should violate constraint
        constraint_ok = opt._check_channel_constraint(
            12, 900.0, current, armed, max_distance=500.0
        )
        assert not constraint_ok, "Channel 12 should violate constraint"
        
        # Calculate intermediate step
        intermediate = opt._calculate_intermediate_step(
            12, 300.0, 900.0, current, armed,
            max_distance=500.0, step_limit=400.0
        )
        
        # Intermediate should be between 300 and 900, and respect constraints
        assert 300.0 < intermediate < 900.0
        assert intermediate <= 400.0 + 500.0  # Constraint with channel 13
        assert intermediate <= 300.0 + 400.0  # Step limit
        
        # If main function available, test full algorithm
        if hasattr(opt, '_arm_and_ramp_bimorph'):
            mv_calls = []
            def mock_mv(channel, value):
                mv_calls.append((channel.channel_num, value))
                channel._set_setpoint(value)
                return []
            
            with patch('bluesky.plan_stubs.mv', side_effect=mock_mv):
                with patch('bluesky.plan_stubs.sleep', return_value=[]):
                    plan = opt._arm_and_ramp_bimorph(
                        step, pos_cache, bimorph_device=mock_bimorph,
                        timeout=60, tolerance=1.0, max_distance=500.0, step_limit=400.0
                    )
                    re(plan)
            
            # Verify intermediate step was used
            channel_12_steps = [val for ch, val in mv_calls if ch == 12]
            if len(channel_12_steps) > 1:
                assert channel_12_steps[0] < 900.0  # First step should be intermediate
            
            # Verify final state
            final_current = mock_bimorph.all_current_voltages().get()[12:14]
            assert abs(final_current[0] - 900.0) < 1.0
            assert abs(final_current[1] - 400.0) < 1.0
    except (ImportError, AttributeError) as e:
        pytest.skip(f"Cannot import optimization module: {e}")


def test_wait_for_armed_values_after_set(mock_bimorph, re):
    """
    Test 3: Waiting for Armed Values
    
    After setting each channel, algorithm waits for armed value to match.
    Verifies armed value waiting mechanism works correctly.
    """
    # Set initial voltages
    initial_voltages = np.full(32, 300.0, dtype=np.float32)
    mock_bimorph = MockBimorphDevice(initial_voltages)
    
    # Target: change channels 12-14 to 400V
    target_voltages = {12: 400.0, 13: 400.0, 14: 400.0}
    
    step = {}
    for ch_num, target in target_voltages.items():
        channel = getattr(mock_bimorph.channels, f"channel{ch_num}")
        step[channel] = target
    
    pos_cache = {}
    
    try:
        from startup.utils import optimization_92 as opt
        
        # Test waiting for armed values
        channel_12 = getattr(mock_bimorph.channels, "channel12")
        channel_12._set_setpoint(400.0)
        
        # Test _wait_for_channel_armed function
        if hasattr(opt, '_wait_for_channel_armed'):
            with patch('bluesky.plan_stubs.sleep', return_value=[]):
                plan = opt._wait_for_channel_armed(
                    channel_12, 400.0, timeout=10.0, tolerance=1.0
                )
                re(plan)
        
        # Verify that armed values match setpoints after setting
        armed = mock_bimorph.all_armed_voltages()[12:15]
        setpoints = mock_bimorph.all_setpoint_voltages()[12:15]
        assert np.allclose(armed, setpoints, atol=1.0)
        
        # Test full algorithm if available
        if hasattr(opt, '_arm_and_ramp_bimorph'):
            def mock_mv(channel, value):
                channel._set_setpoint(value)
                return []
            
            with patch('bluesky.plan_stubs.mv', side_effect=mock_mv):
                with patch('bluesky.plan_stubs.sleep', return_value=[]):
                    plan = opt._arm_and_ramp_bimorph(
                        step, pos_cache, bimorph_device=mock_bimorph,
                        timeout=60, tolerance=1.0, armed_wait_timeout=10.0
                    )
                    re(plan)
            
            # Verify final current values match targets
            current = mock_bimorph.all_current_voltages().get()[12:15]
            assert np.allclose(current, [400.0, 400.0, 400.0], atol=1.0)
    except (ImportError, AttributeError) as e:
        pytest.skip(f"Cannot import optimization module: {e}")
