from collections import deque
from bluesky.examples import motor, det

gs.DETS = [det]

def test():
    scan(motor, 1, 5, 5)

def scan(*args):
    bkp_table_cols = gs.TABLE_COLS

    steps = args[-1]
    params = args[:-1]
    detectors = gs.DETS

    devices = [params[i] for i in range(0, len(params), 3)]

    gs.TABLE_COLS = list(gs.DETS)+devices

    detectors = gs.DETS
    plan = InnerProductAbsScanPlan(detectors, steps, *params)
    plan = fast_shutter_decorator(plan)
    RE(plan, [LiveTable(gs.TABLE_COLS)])

    gs.TABLE_COLS = bkp_table_cols

def dscan(*args):
    bkp_table_cols = gs.TABLE_COLS

    steps = args[-1]
    params = args[:-1]
    detectors = gs.DETS

    devices = [params[i] for i in range(0, len(params), 3)]

    gs.TABLE_COLS = list(gs.DETS)+devices

    detectors = gs.DETS
    plan = InnerProductDeltaScanPlan(detectors, steps, *params)
    plan = fast_shutter_decorator(plan)
    RE(plan, [LiveTable(gs.TABLE_COLS)])

    gs.TABLE_COLS = bkp_table_cols


