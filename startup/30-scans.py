from collections import deque
from bluesky.examples import motor, det

gs.DETS = [det]

def test():
    scan(motor, 1, 5, 5)

def scan(*args):
    bkp_table_cols = gs.TABLE_COLS
    bkp_plot_y = gs.PLOT_Y

    steps = args[-1]
    params = args[:-1]
    detectors = gs.DETS

    devices = [params[i] for i in range(0, len(params), 3)]

    gs.TABLE_COLS = list(gs.DETS)+devices
    gs.PLOT_Y = detectors[0].name

    print("Table Cols:", gs.TABLE_COLS)
    detectors = gs.DETS
    plan = InnerProductAbsScanPlan(detectors, steps, *params)
    RE(plan, [LiveTable(gs.TABLE_COLS), LivePlot(detectors[0])])

    gs.TABLE_COLS = bkp_table_cols
    gs.PLOT_Y = bkp_plot_y

def dscan(*args):
    bkp_table_cols = gs.TABLE_COLS
    bkp_plot_y = gs.PLOT_Y

    steps = args[-1]
    params = args[:-1]
    detectors = gs.DETS

    devices = [params[i] for i in range(0, len(params), 3)]

    gs.TABLE_COLS = list(gs.DETS)+devices
    gs.PLOT_Y = detectors[0].name

    print("Table Cols:", gs.TABLE_COLS)
    detectors = gs.DETS
    plan = InnerProductDeltaScanPlan(detectors, steps, *params)
    RE(plan, [LiveTable(gs.TABLE_COLS), LivePlot(detectors[0])])

    gs.TABLE_COLS = bkp_table_cols
    gs.PLOT_Y = bkp_plot_y

