from time import sleep 
from epics import caget,caput

def mov_all(motor, pos, wait=True, relative=False):
    if relative:
        pos += motor.position
    motor.move(pos, wait=wait)

# Calculate X-ray energy using the current theta position or from given argument    
def getE(bragg=None):
    # Si(111) lattice constant is 5.43095A
    d = 5.43095 
    # q = 2pi / d * sqrt(3.)
    # q = 4pi / lmd * sin(bragg)
    #
    try:
        lmd = 2.0/np.sqrt(3.)*d*np.sin(np.radians(bragg))
    except AttributeError:
        lmd = 2.0/np.sqrt(3.)*d*np.sin(np.radians(mono.bragg.position))
    energy = 1973.*2.*np.pi/lmd
    return energy

# Set energy to the given value, if calc_only=false otherwise only calculate
# when Bragg = 9.6332, Y = -0.1
# ov is the correction needed to get actual Y value
def setE(energy, calc_only=True, ov=-10.243):
    # Si(111) lattice constant is 5.43095A
    d = 5.43095 
    offset = 20.0
    lmd = 1973.*2.*np.pi/energy
    bragg = np.degrees(np.arcsin(lmd*np.sqrt(3.)/(2.*d)))
    y0 = offset/(2.0*np.cos(np.radians(bragg)))
    if calc_only:
        print("expected Bragg angle is %.4f" % bragg)
        print("expected Y displacement is %.4f" % y0)
        print("expected Y motor position after correction is %.4f" % (y0+ov))
        print("run setE(%.1f,calc_only=False) to actually move the mono" % energy)
    else: # this actually moves the motors
        mono.bragg.move(bragg)
        mono.y.move(y0+ov)

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

# move undulator gap
def move_gap(g1):
    # leave limit-check to undulator control
    caput("SR:C16-ID:G1{IVU:1-Mtr:2}Inp:Pos", g1)
    sleep(0.2)
    g1 = caget("SR:C16-ID:G1{IVU:1-Mtr:2}Inp:Pos")
    print("moving to undulator gap of %.3f mm ." % g1)
    sys.stdout.flush()

    # go
    caput("SR:C16-ID:G1{IVU:1-Mtr:2}Sw:Go", 1)
    while True:
        g2 = caget("SR:C16-ID:G1{IVU:1-LEnc}Gap")
        clear_output(wait=True)
        print("current gap is %.3f mm\r" % g2)
        sys.stdout.flush()
        sleep(0.5)
        servo_state = caget("SR:C16-ID:G1{IVU:1-Mtr:1}Sw:Serv-On")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:2}Sw:Serv-On")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:3}Sw:Serv-On")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:4}Sw:Serv-On")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:1}MvSt")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:2}MvSt")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:3}MvSt")
        servo_state += caget("SR:C16-ID:G1{IVU:1-Mtr:4}MvSt")
        #if np.fabs(g1-g2)<0.01:
        if servo_state==0:
            break
        sleep(0.5)
    print("Done. servo_state=%d" % servo_state)

# arcsec to radians conversion
def arcsec_rad(x):
    ## arcsec to rad conversion
    y=x*4.848136811097625
    print(y,"in radians")


# radians to arcsec conversion
def rad_arcsec(x):
    ## arcsec to rad conversion
    y=x/4.848136811097625
    print(y,"in arcsec")

###Solution Enclosure Macros
# flow cell positions
def sam_flow_cell(pos=None):
    '''1 argument accepted: 
        position 1 to 3 from bottrom to top cell.'''
    if not(pos):
        print(flow_pos.__doc__)
    else:
        fps_ref=-0.3
        spac=-4.6
        pos_fps=np.linspace(fps_ref, fps_ref+2*spac,3)
        sc2.set(SC5_SH,0)
        SolExU.move(0)
        sol_en.y.move(pos_fps[pos-1])
        if pos < 0 and pos > 3:
            print("invalid position")
        print("done moving")

def sam_8cell(pos=None):
    '''1 argument accepted: 
        position 1 to 8 from inboard to outboard.'''
    if not(pos):
        print(opencell_pos.__doc__)
    else:
        spac=9
        opencell_ref=-34
        pos_opencell=np.linspace(opencell_ref, opencell_ref+7*-spac,8)
        sc2.set(SC5_SH,0) # move sample handler down
        if pos % 2 == 0:
            sol_en.y.move(-5.25)
            SolExU.move(pos_opencell[pos-1])
            if pos>8:
                print("invalid position")
        else:
            sol_en.y.move(-2.1)
            SolExU.move(pos_opencell[pos-1])
            if pos>8:
                print("invalid position")
        print("done moving")

#upstream needle (row 1) (middle sample cell)
def wash_row(row=None,t2=None,loop=None):
    ''' arguments accepted:
        row --> 1, upstream needle (middle flow cell): 2, downstream needle (top flow cell)
        drying time (s)
        no of wash/dry cycles.'''
    if not(row and t2 and loop):
        print(wash_row.__doc__)
    else:
        if row==1:
            sol_ctrl.pump_mvA(75) ## push the sample back in the pcr tube
            sleep(7)
            sol_ctrl.sv_pcr_tubes.set(0) ## move  sample handler down
            sh.move(0) # position the needle on drain location
            sol_ctrl.vc_4port.set(1) # selects position 4 port on VICI
            sleep(1)
            sol_ctrl.sv_pcr_tubes.set(1) ## move  sample handler up
            sleep(1)
            for n in range (1,loop+1):
                print("current wash/dry loop",n)
                sol_ctrl.sv_sel.set("water") # select water port
                sleep(1)
                sol_ctrl.water_pump.set("on") # start washing
                sleep(0.9) # washing time
                sol_ctrl.sv_drain1.set("on") # vaccum pump on drain1 selected
                sleep(1)
                sol_ctrl.water_pump.set("off")    # stop washing
                sleep(1)
                sol_ctrl.sv_sel.set("N2") # select dry nitrogen port
                sleep(1)
                sol_ctrl.sv_N2.set("on") # start drying
                sleep(t2) # drying time
                sol_ctrl.sv_N2.set("off") # turn dry nitrogen off
                sleep(1)
                sol_ctrl.sv_drain1.set("off") # turn off drain
                sleep(1)
                sol_ctrl.sv_sel.set("water") # back to water port
            sol_ctrl.sv_pcr_tubes.set(0) ## move  sample handler down        
            sleep(1)
        if row==2:
            sol_ctrl.pump_mvA(75) ## push the sample back in the pcr tube
            sleep(7)
            sol_ctrl.sv_pcr_tubes.set(0) ## move  sample handler down
            sh.move(0) # position the needle on drain location
            sol_ctrl.vc_4port.set(0) # selects position 4 port on VICI -- drain 2
            sleep(1)
            sol_ctrl.sv_pcr_tubes.set(1) ## move  sample handler down
            sleep(1)
            #sc1.set(SC5_Drain2,1) # vaccum pump on drain2 selected
            for n in range (1,loop+1):
                sol_ctrl.sv_sel.set("water") # select water port
                sleep(1)
                sol_ctrl.water_pump.set("on") # start washing
                sleep(0.9) # washing time
                sol_ctrl.water_pump.set("off")    # stop washing
                sleep(1)
                sol_ctrl.sv_drain2.set("on") # vaccum pump on drain1 selected
                sleep(1)
                sol_ctrl.sv_sel.set("N2") # select dry nitrogen port
                sleep(1)
                sol_ctrl.sv_N2.set("on") # start drying
                sleep(t2) # drying time
                sol_ctrl.sv_N2.set("off") # turn dry nitrogen off
                sleep(1)
                sol_ctrl.sv_drain2.set("off") # turn off drain
                sleep(1)
                sol_ctrl.sv_sel.set("water") # back to water port
                print("current wash/dry loop",n+1)
            sleep(1)
            sol_ctrl.sv_pcr_tubes.set(0) ## move  sample handler down        
            sleep(1)



def load_sample(row=None,pos=None):
    '''2 arguments accepted:
        row --> 1, upstream needle (middle flow cell): 2, downstream needle (top flow cell)
        pos --> 1 to 6 from inboard to outboard.'''
    if not(row and pos):
        print(load_sample.__doc__)
    else:
        if row==1:
            sp=9 # pcr tube spacing#
            pos_sh=np.linspace(-70, -70-5*sp,6)
            sol_ctrl.sv_pcr_tubes.set(0) ## move the sample loader down before moving sh in x direction
            sleep(1)
            sh.move(0) # keep the needle at drain position and fill the needle upto the flow cell
            sol_ctrl.vc_4port.set(0) ## cell connected to no 4 on 4 port valve
            sleep(1)
            sol_ctrl.valve_pos.set("res")
            sleep(1)
            sol_ctrl.pump_mvA(150)
            sleep(7)
            sol_ctrl.valve_pos.set("sam")
            sleep(1)
            sol_ctrl.pump_mvA(75) ## fill the tubing with water only upto the end of the flow channel
            sleep(7)
            #move the needle to the sample position
            sh.move(pos_sh[pos-1])
            sol_ctrl.sv_pcr_tubes.set(1) ## move the sample loader up
            sleep(1)
            sol_ctrl.pump_mvA(170)
#            pp.umvA(160) ## fill the tubing with water only upto the end of the flow channel
        if row==2:
            sp=9 # pcr tube spacing#
            pos_sh=np.linspace(-16, -16-5*sp,6)
            sol_ctrl.sv_pcr_tubes.set(0) ## move the sample loader down before moving sh in x direction
            sleep(1)
            sh.move(0) # keep the needle at drain position and fill the needle upto the flow cell
            sol_ctrl.vc_4port.set(1) ## switch port to select row 2 sample pickup
            sleep(1)
            sol_ctrl.valve_pos.set("res")
            sleep(1)
            sol_ctrl.pump_mvA(150)
            sleep(7)
            sol_ctrl.valve_pos.set("sam")
            sleep(1)
            sol_ctrl.pump_mvA(75) ## fill the tubing with water only upto the end of the flow channel
            sleep(7)
            #move the needle to the sample position
            sh.move(pos_sh[pos-1])
            sol_ctrl.sv_pcr_tubes.set(1) ## move the sample loader up
            sleep(1)
            sol_ctrl.pump_mvA(170)    


def load_wash(row=None,pos=None,t1=None,t2=None,loop=None):
    '''2 arguments accepted: 
        row --> 1, upstream needle (middle flow cell): 2, downstream needle (top flow cell)
        row =1 - will wash load sample from row 1 and wash row 2 and vice versa
        pos --> 1 to 6 from inboard to outboard.
        washing time (s)
        drying time (s)
        no of wash/dry cycles.'''
    if not(row or pos):
        print(load_wash.__doc__)
    else:
        if row==1:
            pp.umvA(46) ## push the sample in row 2 back to the pcr tube
            load_sample(row,pos)
            wash(2,t1,t2,loop)
        if row==2:
            pp.umvA(60) ## push the sample in row 1 back to the pcr tube
            load_sample(row,pos)
            wash(1,t1,t2,loop)

def sam_out():
    sol_ctrl.sv_pcr_tubes.set(0)## move  sample handler down
    sh.move(50) # move sample handler close to the loadlock door
    sol_ctrl.sv_door_lower.set(1) ## open loadlock door
    sh.move(78.5) # move sample handler out

def sam_in():
    sh.move(50) # move sample handler close to the loadlock door
    sol_ctrl.sv_door_lower.set(0) ## open loadlock door
    sh.move(0) # move sample handler out

def sam_flowcell_in():
    sc2.set(SC5_SH,0) ## move  sample handler down
    SolExU.move(0)


def sh_out():
    sol_ctrl.sv_pcr_tubes.set(0)## move  sample handler down
    sh.move(50) # move sample handler close to the loadlock door
    sol_ctrl.sv_door_lower.set(1) ## open loadlock door
    sh.move(77.5) # move sample handler out

def sh_in():
    sh.move(50) # move sample handler close to the loadlock door
    sol_ctrl.sv_door_lower.set(0) ## open loadlock door
    sh.move(0) # move sample handler out

def meas_8cell(exp,pos,times):
    '''3 arguments accepted:
    exp --> exposure time
    pos = open cell position (1 to 8 from inboard to outboard)
    times = no of measurments'''
    if not(exp or pos or times):
        print(meas_8cell.__doc__)
    else:
        pil1M.cam.acquire_time.put(exp)
        pilW1.cam.acquire_time.put(exp)
        pilW2.cam.acquire_time.put(exp)
        pilatus_number_reset(False)
        sam_8cell(pos)
        d=-8
        a=8
        movr(SolExU,4)
        for n in range(times):
            SolExU.velocity.put(a/(exp+0.5))
            mov_all(SolExU,d,wait=False,relative=True)
            RE(ct(num=1))
            d=-d
        SolExU.velocity.put(0)
        sam_8cell(pos)
        pilatus_number_reset(True)

#{old code
#def meas_SOL(exp, times, v):
    '''3 arguments accepted:
    exp --> exposure time
    times = no of measurments
    volume = volume of flow in one shot'''
    if not(exp or times or v):
        print(meas_SOL.__doc__)
    else:
        for n in range(times):
            pil1M.cam.acquire_time.put(exp)
            pilW1.cam.acquire_time.put(exp)
            pilW2.cam.acquire_time.put(exp)
            pilatus_number_reset(False)
            pp.slow_move(exp,v)
            RE(ct(num=1))
            v=-v
            pilatus_number_reset(True)
            #print(filename)
#        pp.umvA(160) old code}

def meas_SOL(exp, v, times):
    '''3 arguments accepted:
    exp --> exposure time
    v --> volume
    times = no of measurments
    '''
    if not(exp or v or times):
        print(meas_SOL.__doc__)
    else:
        pil1M.cam.acquire_time.put(exp)
        pilW1.cam.acquire_time.put(exp)
        pilW2.cam.acquire_time.put(exp)
        pilatus_number_reset(False)
        sol_ctrl.pump_spd.set(v*60/exp)
        for n in range(times):
            sleep(exp)
            sol_ctrl.pump_mvR(v)
            RE(ct(num=1))
            v=-v
        pilatus_number_reset(True)
        sol_ctrl.pump_spd.set(1500)
        sol_ctrl.pump_mvA(170)

def meas_flowcell(exp, times, v):
    '''3 arguments accepted:
    exp --> exposure time
    times = no of measurments
    volume = volume of flow in one shot'''
    if not(exp or times or v):
        print(meas_flowcell.__doc__)
    else:
        pil1M.cam.acquire_time.put(exp)
        pilW1.cam.acquire_time.put(exp)
        pilW2.cam.acquire_time.put(exp)
        pilatus_number_reset(False)
        pp.slow_move(exp*times,v)
        RE(ct(num=times))
    pp.umvA(160)

def ct_time(exp):
    pil1M.cam.acquire_time.put(exp)
    pilW1.cam.acquire_time.put(exp)
    pilW2.cam.acquire_time.put(exp)

        
