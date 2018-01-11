from ophyd import (EpicsSignal, Device, Component as Cpt)
from time import sleep
import threading
from epics import PV
from scipy import misc
import numpy as np

import bluesky.plans as bp


class RefScan():
    
    def refscan(self, sample_name="none", rx_range=20000, Nx=20, cts=1, attenuation=None):
        
        RE.md['sample_name'] = sample_name 
        RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
        RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
        RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs1_y':waxs2.y.position, 'waxs1_z':waxs2.z.position}) 
        RE.md['energy'] = ({'mono_bragg': mono.bragg.position, 'energy': getE(), 'gap': get_gap()})
        RE.md['Att_fraction']=Attn.att_factor
        #RE.md['XBPM'] = XBPM_pos() 
        mov(waxs1.x, 103.82)
        gs.DETS=[em1, em2, pilW1_ext]
        pilatus_ct_time(cts)
        
        if attenuation==None:
            change_sample(sample_name)
            set_pil_num_images(Nx)
            RE(bp.scan(gs.DETS, tilt.rx, 0.01, rx_range, Nx-1))
      
        else:
            change_sample(sample_name+"_a")
            Attn.fraction(20)
            steps=rx_range/Nx
            nosa=round(2000/steps)
            #print(nosa)
            set_pil_num_images(nosa)
            RE(bp.scan(gs.DETS, tilt.rx, 0.01, 2000, nosa-1))
            
            change_sample(sample_name+"_b")
            Attn.fraction(60)
            steps=rx_range/Nx
            range=7000-2000
            nos=round(range/steps)
            #print(nos)
            set_pil_num_images(nos)
            RE(bp.scan(gs.DETS, tilt.rx, 2000, 7000, nos-1))
            
            change_sample(sample_name+"_c")
            Attn.fraction(100)
            steps=rx_range/Nx
            rangec=rx_range-7000
            nosc=round(rangec/steps)
            #print(nosc)
            set_pil_num_images(nosc)
            RE(bp.scan(gs.DETS, tilt.rx, 7000, rx_range, nosc-1))
            print(db[-3].start.uid)
            print(db[-2].start.uid)
            print(db[-1].start.uid)
            
      
    def rgscan(self, sample_name="none", rx_range=20000, Nx=20, cts=1, attenuation=None):
        
       
        RE.md['sample_name'] = sample_name 
        RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
        RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
        RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs1_y':waxs2.y.position, 'waxs1_z':waxs2.z.position}) 
        RE.md['energy'] = ({'mono_bragg': mono.bragg.position, 'energy': getE(), 'gap': get_gap()})
        RE.md['Att_fraction']=Attn.att_factor
        
        gs.DETS=[em1, em2, pilW1_ext]
        pilatus_ct_time(cts)
        
        mov(waxs1.x, 103.82)
        
        if attenuation==None:
            change_sample(sample_name)
            set_pil_num_images(Nx)
            RE(bp.scan(gs.DETS, tilt.rx, 0.01, rx_range, Nx-1))
            
        else:
            change_sample(sample_name+"_a")
            Attn.fraction(30)
            steps=rx_range/Nx
            nosa=round(4000/steps)
            #print(nosa)
            set_pil_num_images(nosa)
            RE(bp.scan(gs.DETS, tilt.rx, 0.01, 4000, nosa-1))
            
            change_sample(sample_name+"_b")
            Attn.fraction(70)
            steps=rx_range/Nx
            range=10000-4000
            nos=round(range/steps)
            #print(nos)
            set_pil_num_images(nos)
            RE(bp.scan(gs.DETS, tilt.rx, 4000, 10000, nos-1))
            
            change_sample(sample_name+"_c")
            Attn.fraction(100)
            steps=rx_range/Nx
            rangec=rx_range-10000
            nosc=round(rangec/steps)
            #print(nosc)
            set_pil_num_images(nosc)
            RE(bp.scan(gs.DETS, tilt.rx, 10000, rx_range, nosc-1))
       
        #mov(waxs1.x, 63.82)
        gs.DETS=[em1, em2, pil1M_ext]
        pilatus_ct_time(cts)
        mov(tilt.rx, 650)
        set_pil_num_images(5)
        change_sample(sample_name+"gis")
        RE(bp.count(gs.DETS, num=1))
        print(db[-4].start.uid)
        print(db[-3].start.uid)
        print(db[-2].start.uid)
        print(db[-1].start.uid)
        
    def det_in(self):
        mov(waxs1.x, 103.82)
        gs.DETS=[em1, em2, pilW1_ext]
        pilatus_ct_time(1)
        
    
    def det_out(self):
        mov(waxs1.x, 63.82)
        gs.DETS=[em1, em2, pil1M_ext]
        pilatus_ct_time(1)
        
        
    def giscan(self,sample_name="none",cts=1):
        mov(waxs1.x, 63.82)
        gs.DETS=[em1, em2, pil1M_ext]
        cta=cts*5
        pilatus_ct_time(cta)
        mov(tilt.rx, 650)
        set_pil_num_images(5)
        change_sample(sample_name+"gis")
        RE(bp.count(gs.DETS, num=1))
        
    
    #def scan(self, sname="none", rx_range=20000, xrange=2, Nx=20, cts=1, attenuation=None):
    #    a=0
    #    refx=ss2.x.position
    #    for i in range(-xrange,xrange+1,1):
    #        a +=1
    #        sample_name=sname+np.str(a)
    #        mov(ss2.x, i)
    #        self.rgscan(sample_name, rx_range, Nx, cts, attenuation)
    #    mov(ss2.x,refx)
        
    #def scan(self, sname="none", rx_range=20000, xrange=2, Nx=20, cts=1, attenuation=None):
    #    a=0
    #    refx=ss2.x.position
    #    for i in range(-xrange,xrange+1,1):
    #        a +=1
    #        sample_name=sname+np.str(a)
    #        mov(ss2.x, i)
    #        self.refscan(sample_name, rx_range, Nx, cts, attenuation)
    #    a=0
    #    for i in range(-xrange,xrange+1,2):
    #        a +=1
    #        sample_name=sname+np.str(a)
    #        mov(ss2.x, i+0.5)
    #        self.giscan(sample_name)
    #    mov(ss2.x,refx)
    #    print(db[-14].start.uid)
    #    print(db[-13].start.uid)
    #    print(db[-12].start.uid)
    #    print(db[-11].start.uid)
    #    print(db[-10].start.uid)
    #    print(db[-9].start.uid)
    #    print(db[-8].start.uid)
    #    print(db[-7].start.uid)
    #    print(db[-6].start.uid)
    #    print(db[-5].start.uid)
    #    print(db[-4].start.uid)
    #    print(db[-3].start.uid)
    #    print(db[-2].start.uid)
    #    print(db[-1].start.uid)
        
    def scan(self, sname="none", rx_range=20000, xrange=2, no_steps=3, Nx=20, cts=1, attenuation=None):
        a=0
        refx=ss2.x.position
        for i in np.linspace(-xrange,xrange,no_steps):
            a +=1
            print(a)
            sample_name=sname+np.str(a)
            mov(ss2.x, i)
            self.refscan(sample_name, rx_range, Nx, cts, attenuation)
        b=0
        for i in range(-xrange,xrange+1,2):
            b +=1
            print(b)
            sample_name=sname+np.str(b)
            mov(ss2.x, i+0.5)
            self.giscan(sample_name)
        mov(ss2.x,refx)
        c=a*3
        c +=b
        #print(db[-12].start.uid)
        #print(db[-11].start.uid)
        #print(db[-10].start.uid)
        #print(db[-9].start.uid)
        #print(db[-8].start.uid)
        #print(db[-7].start.uid)
        #print(db[-6].start.uid)
        #print(db[-5].start.uid)
        #print(db[-4].start.uid)
        #print(db[-3].start.uid)
        #print(db[-2].start.uid)
        #print(db[-1].start.uid)
        for i in range(-c,0):
            #print(c)
            #print(i)
            print(db[i].start.uid)
            
    
    def ct1(self):
        mov(waxs1.x, 63.82)
        gs.DETS=[em1, em2, pil1M_ext]
        pilatus_ct_time(1)
        mov(tilt.rx, 650)
        set_pil_num_images(5)
        change_sample("test")
        RE(bp.count(gs.DETS, num=1))

    
    
           
rscan= RefScan()
        


           
           
    
            

            
