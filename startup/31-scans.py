from collections import deque
from bluesky.examples import motor, det
from bluesky.spec_api import ct, a2scan, d2scan, mesh

ct = fast_shutter_decorator()(ct)
scan = fast_shutter_decorator()(a2scan)
dscan = fast_shutter_decorator()(d2scan)
mesh = fast_shutter_decorator()(mesh)

gs.DETS = [det]


