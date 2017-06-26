from time import sleep 
from epics import caget,caput
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
import time

def mov_all(motor, pos, wait=True, relative=False):
    if relative:
        pos += motor.position
    motor.move(pos, wait=wait)

def ct_time(exp):
    pil1M.cam.acquire_time.put(exp)
    pilW1.cam.acquire_time.put(exp)
    pilW2.cam.acquire_time.put(exp)
    
def get_uid():
    global B
    B=[]
    header=db[-1]
    a=header.start.uid
    B.append(a)
    with open('test.txt', 'w') as out_file:
        out_file.write('\n'.join(B))
    print(B)
    
def snapshot(camera, showWholeImage=False, ROIs=None):
    img = np.asarray(camera.image.array_data.value).reshape([camera.image.array_size.height.value, 
                                                            camera.image.array_size.width.value])
    # demosaic first
    if showWholeImage:
        plt.imshow(img)
    # show ROIs
    if ROIs==None: return
    # ROI definition: [MinX, SizeX, MinY, SizeY]
    plt.figure()
    n = len(ROIs)
    for i in range(n):
        plt.subplot(1,n,i+1)
        plt.imshow(img[ROIs[i][2]:ROIs[i][2]+ROIs[i][3],ROIs[i][0]:ROIs[i][0]+ROIs[i][1]])
    plt.show()

def set_voltage(chn):
    zorig = caget('XF:16IDA-OP{Mir:KB-PS}:U%d_CURRENT_MON' % chn)
    #caput('XF:16IDA-OP{Mir:KB-PS}:U_STEP', step)
    caput('XF:16IDA-OP{Mir:KB-PS}:INCR_U_CMD.A', chn)
    zchange = caget('XF:16IDA-OP{Mir:KB-PS}:U%d_CURRENT_MON' % chn)
    print("current voltage is %.3f mm\r" % zchange)
    print("done")
    
def reset_voltage(chn):
    zchange = caget('XF:16IDA-OP{Mir:KB-PS}:U%d_CURRENT_MON' % chn)
    #caput('XF:16IDA-OP{Mir:KB-PS}:U_STEP', step)
    caput('XF:16IDA-OP{Mir:KB-PS}:DECR_U_CMD.A', chn)
    zorig = caget('XF:16IDA-OP{Mir:KB-PS}:U%d_CURRENT_MON' % chn)
    print("reseted voltage to %.3f mm\r" % zorig)
    print("done")
    
def Bi_vert_scan(filename="none"):
    # Increaments/Decreaments Voltage on each vertical mirror channel, while scanning the vertical slits
    #sv_avg=np.zeros(steps+4, order='F') # zero array for averaging over the centroid
    gs.DETS=[cam05]
    d = {}
    d_t = {}
    vert_scan=[]
    #sv_avg=np.zeros(steps+4, order='F') # zero array for averaging over the centroid
    s_avg=np.zeros(220+1,order='F')
    gs.DETS=[cam05]
    step=10
    for v in range (12,24):
        set_voltage(v)
        print("****************************************************")
        print(v)
        print("****************************************************")
        #RE(dscan(mps.bottom, 0, bot_scan_high, mps.top, 0, top_range, scan_steps-1))
        RE(dscan(mps.bottom, 0, -2.2, mps.top, 0, 2.2, 220))
        header, data = fetch_scan()
        s_pos = data['mps_top']
        s_data = data['cam05_stats1_centroid_y']
        #sv_avg=(sv_avg+s_data)
        #print(s_avg)
        #sv_avg=sv_avg/i
        #o=scan_steps-1
        o=220-1
        s_avgc = []
        s_posc = []
        for i in range (1,o):
            s_avgc.append(s_data[i])
            s_posc.append(s_pos[i])
            #print(s_avgc)
        d[v]=s_avgc
        vert_scan.append(d[v])
        reset_voltage(v)
    #    ver_scanc=s_posc,s_avgc # appending the data in two columns for vertical scan
    #np.savetxt('/GPFS/xf16id/Commissioning/2017Mar/vert_scan_%d_v2.dat'  % v, vert_scan, delimiter="\t")
    #    print("saved")
    # move slits back to original positions

    mps.top.move(4)
    mps.bottom.move(4)
    data=([s_posc,d[12],d[13],d[14],d[15],d[16],d[17],d[18],d[19],d[20],d[21],d[22],d[23]])
    sdata=np.transpose(data)
    np.savetxt('%s' %filename, sdata,delimiter=',')