
from epics import caget,caput
from IPython.display import display, clear_output
from time import sleep 

"""

# take snapshot on SCN1
def snapcam01():
    C1ROI1 = [290, 200, 225, 150]
    gs.DETS = [cam01]
    setROI(cam01, [C1ROI1])

    # need to set exposure time to 0.001
    caput('XF:16IDA-BI{FS:1-Cam:1}AcquireTime', 0.01)
    sleep(1)
    sp1 = snapshot(cam01, showWholeImage=True, ROIs=[C1ROI1], showROI=False)[0]
    caput('XF:16IDA-BI{FS:1-Cam:1}AcquireTime', 1.0)
    sleep(1)
    sp2 = snapshot(cam01, showWholeImage=False, ROIs=[C1ROI1], showROI=False)[0]


# take snapshot on SCN6


def snapcam06():
    #C1ROI1 = [0, 1935, 0, 1455]
    gs.DETS = [cam06]
    #setROI(cam06)#, [C1ROI1])

    # need to set exposure time to 0.001
    #caput('XF:16IDA-BI{FS:1-Cam:1}AcquireTime', 0.01)
    #sleep(1)
    sp1 = snap(cam06, showWholeImage=True)#, showROI=True)[0]
    #caput('XF:16IDA-BI{FS:1-Cam:1}AcquireTime', 1.0)
    #sleep(1)
    #sp2 = snapshot(cam01, showWholeImage=False, ROIs=[C1ROI1], showROI=False)[0]
"""