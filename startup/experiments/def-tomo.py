import os,threading,time
from ophyd import EpicsSignal
from PIL import Image,ImageDraw,ImageChops
from bluesky.suspenders import SuspendFloor

import cv2
from matplotlib.patches import Rectangle

EMconfig = EpicsSignal("XF:16IDC-ES:EMconfig")
EMconfig.put('scanning')

# beam height is 0, out position is 418.5
try:
    print("sdd_y defined:", sdd_y)
except:
    sdd_y = EpicsMotor("XF:16IDC-ES:Scan{Ax:SDD-y}Mtr", name="sdd_y")

# set these in the IOC 
#caput('XF:16IDC-ES:Scan2-Gonio{Ax:tX}Mtr.MRES', 1e-5)
#caput('XF:16IDC-ES:Scan2-Gonio{Ax:tZ}Mtr.MRES', 1e-5)

# robot-related PVs
#    setting the StagePresent PV: XF:16IDC-ES:LIX{CS8}BeadStagePresent
#    setting the sample present PV: XF:16IDC-ES:LIX{CS8}Bead01_sts
# might need to first run rbt.resetSoftIO()
ready_for_robot([],[],init=True)

try:
    print("camES2 defined:", camES2)
except:
    camES2 = setup_cam("camES2")
camES2.ext_trig = True

# NOTE: ss.xc zero position reset, ref position changed by 22mm on 02/29/24s
#       SC has changed the record in the motor spreadsheets
# park position was 85, measuremnet position was 22s
def move_sample(pos=None, use_XSP3=False, use_robot=True):
    if pos=="park":
        # must move the SDD out of the way first
        sdd_y.move(415)
        if use_robot:
            #ready_for_robot([ss.xc, ss.sx, ss.sz, ss.x, ss.y, ss.z, ss.ry, sdd_y],
            #                [63,    0,     0,     0,    0,    6,   -90,  415])
            ready_for_robot([ss.xc, ss.tx, ss.tz, ss.sx, ss.sz, ss.x, ss.y, ss.z, ss.ry, sdd_y],
                            [63,    0,     0,     0,     0,     0,    0,    6,   -90,  415])
        else:
            ss.xc.move(63)
            ss.ry.move(-90)
            ss.z.move(6)
    else:
        if use_robot:
            rbt.goHome()    # robot must be out of the way for SDD to come down 
        ss.z.move(6)  # 7.5
        ss.xc.move(0)
        if use_XSP3:
            sdd_y.move(0)

def unmount_sample(n):
    move_sample('park')
    rbt.unmountBead()
    rbt.unloadBead(n)
        
def mount_sample(n, pos_sx=0, pos_sz=0, pos_tx=0, pos_tz=0, measure=True, use_XSP3=False):
    if ready_for_robot.EMready.get()==0:
        raise Exception("robot not ready ...")
    if sdd_y.position<400:
        raise Excpetion("SDD in the way ...")  #sdd_y.move(415)   
    rbt.loadBead(n)
    rbt.mountBead()

    ss.sx.move(pos_sx)
    ss.sz.move(pos_sz)
    ss.tx.move(pos_tx)
    ss.tz.move(pos_tz)    
    
    if measure:
        move_sample(use_XSP3=use_XSP3)    

def test_flying(exp_time, dx=0.2, Nx=20, dy=0.1, Ny=10):
    x0 = ss.x.position
    y0 = ss.y.position


    change_sample()
    RE(raster(exp_time, ss.x, x0, x0+dx, Nx, ss.y, y0, y0+dy, Ny, detectors=[pil,em1ext,em2ext,xsp3]))

    ss.x.move(x0)
    ss.y.move(y0)


def collect_large_map(sname, x1, x2, y1, y2, step_size_x=0.1, step_size_y=0.1, 
                exp_time=0.2, check_beam=True, use_XSP3=False, md=None):
    """ split the large area into smaller ones, such that total number of frames in each scan is ~10k or fewer
    """
    
    if x1>x2:
        t=x1;x1=x2;x2=t
    
    if y1>y2:
        t=y1;y1=y2;y2=t
    
    dx = x2-x1
    Nx0 = int(dx/step_size_x+0.5)+1
    dy = y2-y1
    Ny0 = int(dy/step_size_y+0.5)+1
    
    _md = {"experiment": "scanning"}
    _md.update(md or {})

    if use_XSP3:
        detectors = [xsp3,pil,em1ext,em2ext]
        makedirs(get_IOC_datapath(xsp3.name, xsp3.hdf.data_dir)+sname, mode=0O777)
    else:
        detectors = [pil,em1ext,em2ext]

    update_metadata()
    pil.use_sub_directory(sname)    

    Nseg = int(Nx0*Ny0/10000)+1    
    if Nx0>Ny0:
        fast_axis = 'x'
        dN = int(Ny0/Nseg)
    else:
        fast_axis = 'y'
        dN = int(Nx0/Nseg)
        
    for i in range(Nseg):
        print(f"{sname}-{i:02d}:  ", end="")
        change_sample(f"{sname}-{i:02d}", exception=False)

        if fast_axis=='x':
            Nx = Nx0
            if i==Nseg-1:
                Ny = Ny0-i*dN
            else:
                Ny = dN
            x1s = x1
            x2s = x2
            y1s = y1+i*dN*step_size_y
            y2s = y1s+(Ny-1)*step_size_y    
        else:
            if i==Nseg-1:
                Nx = Nx0-i*dN
            else:
                Nx = dN
            Ny = Ny0 
            x1s = x1+i*dN*step_size_x
            x2s = x1s+(Nx-1)*step_size_x
            y1s = y1
            y2s = y2  
            
        ss.x.move(x1s)
        ss.y.move(y1s)
        try:
            camES1.saveImg(f"img/{current_sample}_ES1.png")
            time.sleep(0.5)
            camES1.saveImg(f"img/{current_sample}_ES1.png")
        except:
            print("camera issue, ignoring ...")
    
        while check_beam and not verify_beam_on():
            time.sleep(check_bm_period)
    
        if pauseFlag.get():
            print("Pause flag is set, waiting ...")
            k = input("Hit Q to exit, any other key to continue ...")
            setSignal(pauseFlag, 0)
            if k=='Q':
                raise Exception("terminated by user")
    
        print("running raster: ", x1s, x2s, Nx, y1s, y2s, Ny, fast_axis)
        if fast_axis=="x":
            RE(raster(exp_time, ss.x, x1s, x2s, Nx, ss.y, y1s, y2s, Ny, 
                      detectors=detectors, md=_md))
        else:
            RE(raster(exp_time, ss.y, y1s, y2s, Ny, ss.x, x1s, x2s, Nx, 
                      detectors=detectors, md=_md))
            
        print('raster completed.')
        send_to_packing_queue(db[-1].start['uid'], "flyscan")


def collect_map(sname, x1, x2, y1, y2, step_size_x=0.1, step_size_y=0.1, fast_axis="y",
                exp_time=0.2, check_beam=True, use_XSP3=False, md=None):

    if not fast_axis in ['x', 'y']:
        raise Exception(f"unknown fast axis: {fast_axis}")
        
    if x1>x2:
        t=x1;x1=x2;x2=t
    
    if y1>y2:
        t=y1;y1=y2;y2=t
    
    dx = x2-x1
    Nx = int(dx/step_size_x+0.5)+1
    dy = y2-y1
    Ny = int(dy/step_size_y+0.5)+1

    if Nx*Ny>12000:  # limited by XSP3
        raise Exception(f"too many data points: {Nx*Ny}, reduce size of the scan ...")
    
    _md = {"experiment": "scanning"}
    _md.update(md or {})

    if use_XSP3:
        detectors = [xsp3,pil,em1ext,em2ext]
        makedirs(get_IOC_datapath(xsp3.name, xsp3.hdf.data_dir)+sname, mode=0O777)
    else:
        detectors = [pil,em1ext,em2ext]

    update_metadata()
    pil.use_sub_directory(sname)    
    change_sample(f"{sname}", exception=False)
    ss.x.move(x1)
    ss.y.move(y1)
    time.sleep(2)
    try:
        camES1.saveImg(f"img/{current_sample}_ES1.png")
    except:
        print("camera issue, ignoring ...")

    while check_beam and not verify_beam_on():
        time.sleep(check_bm_period)

    if pauseFlag.get():
        print("Pause flag is set, waiting ...")
        k = input("Hit Q to exit, any other key to continue ...")
        setSignal(pauseFlag, 0)
        if k=='Q':
            raise Exception("terminated by user")

    print("running raster: ", x1, x2, Nx, y1, y2, Ny, fast_axis)
    if fast_axis=="x":
        RE(raster(exp_time, ss.x, x1, x2, Nx, ss.y, y1, y2, Ny, 
                  detectors=detectors, md=_md))
    else:
        RE(raster(exp_time, ss.y, y1, y2, Ny, ss.x, x1, x2, Nx, 
                  detectors=detectors, md=_md))
        
    print('raster completed.')
    send_to_packing_queue(db[-1].start['uid'], "flyscan")

def collect_projections(sname, x1, x2, y1, y2, step_size_x=0.1, step_size_y=0.1, 
                        fast_axis='x', phi_list=[0., 45., 90.],
                        exp_time=0.2, check_beam=True, use_XSP3=False, md=None):
    
    for phi in phi_list:   
        sn = f"{sname}-phi{phi:.1f}"
        ss.ry.move(phi)    
        time.sleep(2)
        
        collect_map(sn, x1, x2, y1, y2, step_size_x=step_size_x, step_size_y=step_size_y, 
                    fast_axis=fast_axis,
                    exp_time=exp_time, check_beam=check_beam, use_XSP3=use_XSP3, md=md)   

    
def collect_projections0(sname, x1, x2, y1, y2, step_size_x=0.1, step_size_y=0.1, 
                        phi_list=[0., 45., 90.],
                        exp_time=0.2, check_beam=True, use_XSP3=False, md=None):
    
    if x1>x2:
        t=x1;x1=x2;x2=t
    
    if y1>y2:
        t=y1;y1=y2;y2=t
    
    dx = x2-x1
    Nx = int(dx/step_size_x+0.5)+1
    dy = y2-y1
    Ny = int(dy/step_size_y+0.5)+1
    
    _md = {"experiment": "scanning"}
    _md.update(md or {})
    
    if use_XSP3:
        detectors = [xsp3,pil,em1ext,em2ext]
    else:
        detectors = [pil,em1ext,em2ext]

    update_metadata()
    pil.use_sub_directory(sname)
    if use_XSP3:
        makedirs(get_IOC_datapath(xsp3.name, xsp3.hdf.data_dir)+sname, mode=0O777)
    
    for phi in phi_list:   
        change_sample(f"{sname}-phi{phi:.1f}", exception=False)
        ss.x.move(x1)
        ss.ry.move(phi)    
        time.sleep(2)
        try:
            camES1.saveImg(f"img/{current_sample}_ES1.png")
        except:
            print("camera issue, ignoring ...")

        while check_beam and not verify_beam_on():
            time.sleep(check_bm_period)

        if pauseFlag.get():
            print("Pause flag is set, waiting ...")
            k = input("Hit Q to exit, any other key to continue ...")
            setSignal(pauseFlag, 0)
            if k=='Q':
                raise Exception("terminated by user")

        print("running raster: ", x1, x2, Nx, y1, y2, Ny)
        RE(raster(exp_time, ss.x, x1, x2, Nx, ss.y, y1, y2, Ny, 
                  detectors=detectors, md=_md))
        print('raster completed.')
        send_to_packing_queue(db[-1].start['uid'], "flyscan")
    
    pil.use_sub_directory()
    
        
def collect_tomo(sname, x1, x2, step_size=0.1, Nphi=120, Nseg=1, skip=0, dy=0.0,
                        exp_time=0.2, check_beam=True, use_XSP3=False, md=None):
    
    if not Nphi in [90, 100, 120]:
        print("dphi must be one of 90 (2.0deg), 100 (1.8deg), or 120 (1.5deg)")
        return
    if int(Nphi/Nseg)*Nseg<Nphi:
        print(f"Nphi={Nphi} is not divisible by Nseg={Nseg}")
        return
    
    if x1>x2:
        t=x1;x1=x2;x2=t
    
    dx = x2-x1
    Nx = int(dx/step_size+0.5)+1
    
    dphi = 180./Nphi
    phi_list = np.arange(-90, 90., dphi).reshape(-1, Nseg).T
    Nang = Nphi/Nseg

    if Nx*Nang>12000: # limited by XSP3
        raise Exception(f"too many data points: {Nx*Nang}, increase the number of segments ...")
    
    _md = {"experiment": "scanning"}
    _md.update(md or {})
    
    if use_XSP3:
        detectors = [xsp3,pil,em1ext,em2ext]
        makedirs(get_IOC_datapath(xsp3.name, xsp3.hdf.data_dir)+sname, mode=0O777)
    else:
        detectors = [pil,em1ext,em2ext]

    update_metadata()
    pil.use_sub_directory(sname)
    print("using subdir ", sname)
    
    phi0 = -90
    dn = int(Nphi/Nseg)
    for i in range(Nseg):
        phi0 = phi_list[i][0]
        phi1 = phi_list[i][-1]
        n = len(phi_list[i])
        if i==0:
            phi1 = 90.
            n += 1

        change_sample(f"{sname}-{i:02d}", exception=False)
        ss.x.move(x1)
        ss.ry.move(phi0)    
        time.sleep(2)
        try:
            camES1.saveImg(f"img/{current_sample}_ES1.png")
        except:
            print("camera issue, ignoring ...")
        if i>=skip:
            while check_beam and not verify_beam_on():
                time.sleep(check_bm_period)

            if pauseFlag.get():
                print("Pause flag is set, waiting ...")
                k = input("Hit Q to exit, any other key to continue ...")
                setSignal(pauseFlag, 0)
                if k=='Q':
                    raise Exception("terminated by user")

            print("running raster: ", x1, x2, Nx, phi0, phi1, n)
            RE(raster(exp_time, ss.x, x1, x2, Nx, ss.ry, phi0, phi1, n, 
                      detectors=detectors, md=_md))
            print('raster completed.')
            send_to_packing_queue(db[-1].start['uid'], "flyscan")
        phi0 += (n+1)*dphi
        ss.y.move(ss.y.position+dy)
    
    pil.use_sub_directory()

def get_contour(img, roi=[0, -15, 220, 470], ax=None, rotate=True):
    img0 = np.copy(img[roi[0]:roi[1], roi[2]:roi[3]])
    img1 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    
    cc,bb = np.histogram(img1.flatten(), bins=50)
    thresh = (bb[np.argmax(cc)+1] + np.max(img1))/2
    
    thresh,ret = cv2.threshold(img1, thresh, 255, 0)
    contours,_ = cv2.findContours(ret, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cnt0 = contours[0]
    x0,y0,w0,h0 = cv2.boundingRect(cnt0)
    for cnt in contours[1:]:
        x,y,w,h = cv2.boundingRect(cnt)
        if w*h>w0*h0:
            cnt0 = cnt
            x0,y0,w0,h0 = cv2.boundingRect(cnt0)
    
    if not rotate:
        #box = cv2.boxPoints(cnt0)
        #box = np.int0(box)
        if ax is not None:
            img2 = cv2.rectangle(img0, (x0,y0), (x0+w0,y0+h0), [255,0,0], 2)
            ax.imshow(img2)
        return x0,y0,w0,h0
        
    pos,sz,tt = cv2.minAreaRect(cnt0)
    if tt>10:
        tt -= 90
        sz = np.flip(sz)
    rect0 = (pos, sz, tt)
    box = cv2.boxPoints(rect0)
    box = np.int0(box)
    
    if ax is not None:
        img2 = cv2.drawContours(img0, [box], 0, [255,0,0], 2)
        #ax.clear()
        ax.imshow(img2)
    
    return rect0

def cline(ry, sx0, sz0, c):
    """ ry in deg
    """
    return sx0*np.cos(np.radians(ry-30)) + sz0*np.cos(np.radians(ry+60)) +c

def visual_move_angle(mot, roi=[0, -50, 130, 450], err=0.1):
    """ continue to tilt the sample until the tilt is close to zero
        NOT YET COMPLETED
    """
    print(f"untilting {mot.name}  ...")
    #plt.figure()
    #ax = plt.gca()
    ax = None
    rot0 = 1e4
    while True:
        img = camES2.snapshot()
        (cx,cy),(w,h),rot = get_contour(img, roi=roi, ax=ax)
        if np.fabs(rot)<err:
            break
        if rot0>1e3:
            pass
        elif np.fabs(dx)>np.fabs(dx0):
            print("moving the wrong way?")
            lin_scale *= -1
        else:
            print(f"current position:  {cx:.1f}, to move motor by {dx:.4f}     ")#, end="")
            if np.fabs(cx-cx0)<err:
                break
            RE(mov(mot, -rot*ang_scale/2)) 
        da0 = dx
        time.sleep(1)
    print("\ndone")

def visual_move(mot, cx0, roi=[0, -50, 130, 450], err=1, lin_scale=42.):
    """ continue to move the motor until the center of the object is <err pixels from cx0
    """
    print(f"moving {mot.name} to {cx0:.1f} ...")
    #plt.figure()
    #ax = plt.gca()
    ax = None
    dx0 = 1e4
    while True:
        img = camES2.snapshot()
        x,y,w,h = get_contour(img, roi=roi, rotate=False, ax=ax)
        cx = x+w/2
        dx = (cx-cx0)/lin_scale/2
        if np.fabs(dx)>np.fabs(dx0):
            print("moving the wrong way?")
            lin_scale *= -1
        else:
            print(f"current position:  {cx:.1f}, to move motor by {dx:.4f}     ")#, end="")
            if np.fabs(cx-cx0)<err:
                break
            RE(movr(mot, dx))
        dx0 = dx
        time.sleep(1)
    print("\ndone")

def align_sample(roi=[0, -50, 130, 450], ang_scale=1.3, lin_scale=42., keep_orientation=False):
    """ ROI = [top, bottom, left, right]
        top coordinate is 0
        
        ang_scale due to tx/tz calibration
        lin_scale due to sx/sz calibration (pixel/mm), camera zoom
        
        make sure that camES2 Image1 plugin is enabled
        
    """
    #plt.figure()
    #ax = plt.gca()
    ax = None
    
    if keep_orientation:
       ss.ry.move(-55)
       time.sleep(1)
    else:
       ss.tz.move(0)
       ss.tx.move(0)

       ss.ry.move(35)
       #visual_move_angle(ss.tz, roi=roi, ang_scale=ang_scale)
       time.sleep(1)
       img = camES2.snapshot()
       (cx,cy),(w,h),rot = get_contour(img, roi=roi, ax=ax)
       RE(mov(ss.tz, -rot*ang_scale))  # *2 due to incorrect calibration?
       time.sleep(1)
    
       ss.ry.move(-55)
       time.sleep(1)
       img = camES2.snapshot()
       (cx,cy),(w,h),rot = get_contour(img, roi=roi, ax=ax)
       RE(mov(ss.tx, -rot*ang_scale))  # *2 due to incorrect calibration?
       time.sleep(1)

    
    img = camES2.snapshot()
    x1,y1,w1,h1 = get_contour(img, roi=roi, ax=ax, rotate=False)
    ss.ry.move(125)
    time.sleep(1)
    img = camES2.snapshot()
    x2,y2,w2,h2 = get_contour(img, roi=roi, ax=ax, rotate=False)
    RE(movr(ss.sz, ((x1+w1/2)-(x2+w2/2))/2/lin_scale))
    time.sleep(1)
    #img = camES2.snapshot()
    #x2,y2,w2,h2 = get_contour(img, roi=roi, ax=ax, rotate=False)
    cx = ((x1+w1/2)+(x2+w2/2))/2
    visual_move(ss.sz, cx, roi=roi, lin_scale=-lin_scale)    # sign based on observed behavior
    
    ss.ry.move(35)
    time.sleep(1)
    #img = camES2.snapshot()
    #x3,y3,w3,h3 = get_contour(img, roi=roi, ax=ax, rotate=False)
    #RE(mov(ss.sx, ss.sx.position+(x3+w3/2-cx)/lin_scale))
    visual_move(ss.sx, cx, roi=roi, lin_scale=-lin_scale)    # sign based on observed behavior

