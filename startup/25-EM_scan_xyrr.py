# definitions related to the micro-beam experimental module with 2 Newport translation stages and 2 rotary stages (Newport + SmarAct)
from ophyd import (EpicsSignal, Device, Component as Cpt)
from time import sleep
import threading
from epics import PV
from scipy import misc


class ScanningExperimentalModule2():
    """ the zero for Ry must be set correctly so that Rx is pointing in the x direction
        once homed, this position is at -6.0
    """
    x = EpicsMotor('XF:16IDC-ES:Scan2{Ax:X}Mtr', name='ss2_x')
    y = EpicsMotor('XF:16IDC-ES:Scan2{Ax:Y}Mtr', name='ss2_y')
    z = EpicsMotor('XF:16IDC-ES:InAir{Mscp:1-Ax:F}Mtr', name='focus')
    rx = EpicsMotor('XF:16IDC-ES:Scan2{Ax:RX}Mtr', name='ss2_rx')
    ry = EpicsMotor('XF:16IDC-ES:Scan2{Ax:RY}Mtr', name='ss2_ry')    
    # this is the position of the rotation center relative to the sample position
    # these values should be adjusted carefully in order for self.mv() to work perfectly
    # however just leaving them (particularly cz0) to 0 should work well enough too
    cy0 = 0.
    cz0 = 0.
    
    def __init__(self):
        """ cy0 is the y motor position when the beam hits the Rx axis
        """
        self.sn0_set = False
        
    # call this when the sample is fully within the focal plane (independent of x and y)
    # The sample cannot deviate too much from ideal position, otherwise the two rotary stages
    #    will not be sufficient to re-posiiton it back into the focal (x-y) plane
    def set_sn0(self):
        self.z0 = self.z.position
        self.rx.set_current_position(0)
        self.sn0_set = True
    
    def unset_sn0(self):
        self.sn0_set = False
        
    # once set_sn0() is excuted, the sample position should be changed by Rx only; assume that 
    # the effect of non-zero Ry is minimal and the sample is close to the rotation axes of Rx and Ry 
    # cz0 is the offset of the sample from the rotation axis in z
    def mv(self, x1, y1, rx1, cz0=0):
        if not self.sn0_set:
            print("must run set_sn0() to define sample orientaion first.")
        
        # unit of z (microscopr focus is micron
        # the sign for the correction term is depends on how the signs for the other motions are defined
        #z1 = self.z0 - 1000.*(y1-self.cy0)*np.tan(np.radians(rx1)) 
        #y1 = y1 
        z2 = self.z0 - 1000.*(y1-self.cy0)*np.sin(np.radians(rx1))
        y2 = y1 - (y1-self.cy0)*(1. - np.cos(np.radians(rx1)))
        mov([self.x, self.y, self.z, self.rx], [x1, y2, z2, rx1])
    
    
    # do two scans, at rx0 and -rx0; move y and z so that the center of the ROI is in focus
    # if rx0 is not specified, do one scan only wihtout rotation  
    # more complicated version to follow:
    #     keep sample in focus all the time
    #     revise the scan step size to maintain square (projected) grid on the sample 
    def scan(self, sample_name, dx, dy, Nx, Ny=None, rx0=None):
        if not self.sn0_set:
            print("must run set_sn0() to define sample orientaion first.")
        x1 = self.x.position
        y1 = self.y.position
        r0 = self.rx.position
        if Ny==None:
            Ny=Nx
         
        #d = cam_mic.snapshot(ROIs=[cam_mic.getROI(1)])
        #im1 = Image.fromarray(np.asarray(d[0][:,:,0]))
        
        #gs.DETS=[em1, em2, pil1M_ext,pilW1_ext,pilW2_ext]
        #gs.DETS=[em1, em2, pil1M,pilW1,pilW2]
        set_pil_num_images(Nx*Ny)
        
        if rx0==None:
            change_sample(sample_name)
            RE.md['sample_rotation'] = self.rx.position
            cam_mic.saveImg('%s%s_1.png' % (data_path, current_sample))
            #RE(mesh(self.x, x1-dx/2, x1+dx/2, Nx, self.y, y1-dy/2, y1+dy/2, Ny))
            RE(mesh(self.y, y1-dy/2, y1+dy/2, Ny, self.x, x1-dx/2, x1+dx/2, Nx))
            cam_mic.saveImg('%s%s_2.png' % (data_path, current_sample))            
            mov([self.x, self.y], [x1, y1])
      
        else:
            self.mv(x1, y1, rx0)
            change_sample(sample_name+"_a")
            RE.md['sample_rotation'] = rx0 
            cam_mic.saveImg('%s%s_1.png' % (data_path,current_sample))
            RE(mesh(self.x, x1-dx/2, x1+dx/2, Nx, self.y, y1-dy/2, y1+dy/2, Ny))
            cam_mic.saveImg('%s%s_2.png' % (data_path, current_sample))
       
            self.mv(x1, y1, -rx0)
            change_sample(sample_name+"_b")
            RE.md['sample_rotation'] = -rx0 
            cam_mic.saveImg('%s%s_1.png' % (data_path, current_sample))
            RE(mesh(self.x, x1-dx/2, x1+dx/2, Nx, self.y, y1-dy/2, y1+dy/2, Ny))
            cam_mic.saveImg('%s%s_2.png' % (data_path, current_sample))
            
            self.mv(x1, y1, 0)
      
    def scan1(self, s1, e1, Ny, s2, e2, Nx):
        set_pil_num_images(Nx*Ny)
        RE(mesh(ss2.y, s1,e1, Ny, ss2.x, s2, e2, Nx))

    def scan2(self, s1, e1, Nx, s2, e2, Ny):
        set_pil_num_images(Nx*Ny)
        RE(mesh(ss2.x, s1,e1, Nx, ss2.y, s2, e2, Ny))
    
p1 = PV('XF:16IDC-ES:Scan2{Ax:X}Mtr')    
p2 = PV('XF:16IDC-ES:Scan2{Ax:RX}Mtr')
sleep(1)  # after 2017C1 shtdown, this delay becomes necessary
# cheking just once often did not work
if p1.connect()==False and p1.connect()==False:
    print("Scanning EM #2 is not available: XPS probably not running ...")
elif p2.connect()==False:
    print("Scanning EM #2 is not available: SmarAct 15 probably not running ...")
else:
    ss2 = ScanningExperimentalModule2()

del p1,p2
