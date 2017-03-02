
from epics import caget,caput
from IPython.display import display, clear_output
from time import sleep 


# create a snapshot of given camera
def snapshot(camera, showWholeImage=False, ROIs=None, showROI=False):
    img = np.asarray(camera.image.array_data.value).reshape([camera.image.array_size.height.value, 
                                                            camera.image.array_size.width.value])
    # demosaic first
    if showWholeImage:
        plt.imshow(img)
    # show ROIs
    if ROIs==None: return
    # ROI definition: [MinX, SizeX, MinY, SizeY]
    if showROI: 
        plt.figure()
    n = len(ROIs)
    data = []
    for i in range(n):
        if showROI: 
            plt.subplot(1,n,i+1)
        roi = img[ROIs[i][2]:ROIs[i][2]+ROIs[i][3],ROIs[i][0]:ROIs[i][0]+ROIs[i][1]]
        if showROI: 
            plt.imshow(roi)
        data.append(roi)
    if showROI: 
        plt.show()

    return(data)

# ROIs = [ROI1, ROI2, ...]
# each ROI is defined as [startX, sizeX, startY, sizeY]
def setROI(camera, ROIs):
    for i in range(len(ROIs)):
        caput(camera.prefix+("ROI%d:MinX" % (i+1)), ROIs[i][0]) 
        caput(camera.prefix+("ROI%d:SizeX" % (i+1)), ROIs[i][1]) 
        caput(camera.prefix+("ROI%d:MinY" % (i+1)), ROIs[i][2]) 
        caput(camera.prefix+("ROI%d:SizeY" % (i+1)), ROIs[i][3])


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

# create a snapshot of given camera
def snap(camera, showWholeImage=False, ROIs=None, showROI=False):
    img = np.asarray(camera.image.array_data.value).reshape([camera.image.array_size.depth.value,
                                                             camera.image.array_size.height.value,
                                                             camera.image.array_size.width.value])
    # demosaic first
    if showWholeImage:
        plt.imshow(img)
    # show ROIs
    if ROIs==None: return
    # ROI definition: [MinX, SizeX, MinY, SizeY]
    if showROI: 
        plt.figure()
    n = len(ROIs)
    data = []
    for i in range(n):
        if showROI: 
            plt.subplot(1,n,i+1)
        roi = img[ROIs[i][2]:ROIs[i][2]+ROIs[i][3],ROIs[i][0]:ROIs[i][0]+ROIs[i][1]]
        if showROI: 
            plt.imshow(roi)
        data.append(roi)
    if showROI: 
        plt.show()

    return(data)

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
