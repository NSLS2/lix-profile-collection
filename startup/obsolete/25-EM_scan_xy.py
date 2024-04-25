from ophyd import (EpicsSignal, Device, Component as Cpt)
from time import sleep
import threading
from epics import PV
from scipy import misc
import numpy as np
import bluesky.plans as bp
from bluesky import Msg



class ScanningExperimentalModule1():
    
    x = EpicsMotor('XF:16IDC-ES:InAir{Stg:ScanF-Ax:X}Mtr', name='smf_x')
    y = EpicsMotor('XF:16IDC-ES:InAir{Stg:ScanF-Ax:Y}Mtr', name='smf_y')
    
    
    
    def mscan(self, sample_name="none", mtr1="x", s1=-50, e1=50, mtr2="y", s2=-50, e2=50, Nx=5, Ny=5, cts=2):
        
        RE.md['sample_name'] = sample_name 
        RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
        RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
        RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs1_y':waxs2.y.position, 'waxs1_z':waxs2.z.position}) 
        RE.md['energy'] = ({'mono_bragg': mono.bragg.position, 'energy': getE(), 'gap': get_gap()})
        #RE.md['Att_fraction']=Attn.att_factor
        #RE.md['XBPM'] = XBPM_pos() 
        
        change_sample(sample_name)
        DETS=[em1, em2, pilW1_ext,pilW2_ext,pil1M_ext]
        set_pil_num_images(Nx*Ny)
        pilatus_ct_time(cts)
        

        if mtr1=='x':
            RE(grid_scan_fs(DETS, 
                                     smf.x, s1, e1, Nx, 
                                     smf.y, s2, e2, Ny, False, 
                                     per_step=one_nd_step_with_shutter))
        else:
            RE(grid_scan_fs(DETS, 
                                     smf.y, s1, e1, Nx, 
                                     smf.x, s2, e2, Ny, False, 
                                     per_step=one_nd_step_with_shutter))
        mov(smf.x, 0)
        mov(smf.y, 0)
     
            
    def sam_pos(self,pos):
        pos_list1=[0.54, -9.06, -18.7, 0.54, -9.06, -18.7]
        pos_list2=[0, 12.5]
        
        if pos <= 3:
            mov(smc.y,pos_list1[pos-1])
            mov(smc.x, pos_list2[1-1])
            #print(pos_list1[pos-1])
            #print(pos_list2[1-1])
            
        elif pos >=4 & pos <=6:
            mov(smc.y,pos_list1[pos-1])
            mov(smc.x, pos_list2[2-1])
            #print(pos_list1[pos-1])
            #print(pos_list2[2-1])
          
        else:
            print("invalid position")
          
        
    def sam_in(self):
        mov(smc.y, -7.3)
        mov(smc.x, 7.3)
    
    def sam_out(self):
        mov(smc.x, 30)
        
        
    
           
ss1= ScanningExperimentalModule1()
        


           
           
    
            

            
