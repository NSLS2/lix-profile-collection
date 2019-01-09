from collections import deque
from ophyd.sim import motor, det
import bluesky.plans as bp

# NOTE: 
# the syntax for asca/dscan is:   ascan(detecotrs, n_steps, motro1, start1, end1, ...)
# the syntax for mesh is:         mesh(detectors, motor1, start1, end1, nstep1, ...)

ascan = fast_shutter_decorator()(bp.scan)
dscan = fast_shutter_decorator()(bp.rel_scan)
ct = fast_shutter_decorator()(bp.count)
mesh = fast_shutter_decorator()(bp.grid_scan)

