print(f"Loading {__file__}...")

import os
from ophyd import (EpicsSignal, Device, Component as Cpt)
from time import sleep
import threading
from epics import PV


profile_dir = get_ipython().profile_dir.location

#at = np.genfromtxt(os.path.join(profile_dir, "data_files/attn_comb"),skip_header=0)
#t1p = np.genfromtxt(os.path.join(profile_dir, "data_files/atn1x_pos_per.dat"),delimiter=',',skip_header=0)
#t2p = np.genfromtxt(os.path.join(profile_dir, "data_files/atn2x_pos_per.dat"),delimiter=',',skip_header=0)
#t3p = np.genfromtxt(os.path.join(profile_dir, "data_files/atn3x_pos_per.dat"),delimiter=',',skip_header=0)


class Attenuator():
    def fraction(self, a):
        if a!=0:
            factor=a/100
            j=min(range(len(at)), key = lambda i:abs(at[i]-factor))
            i=0
            for h in range(0,36):
                if i==j:
                    break
                for k in range(0,17):
                    if i ==j:
                        break
                    for l in range(0, 77):
                        i +=1
                        if i==j:
                            break
            a=t1p[h-1,0]
            b=t2p[k-1,0]
            c=t3p[l-1,0]
            self.att_factor=1/at[j]
            mov([atn1x, atn2x, atn3x],[a,b,c])
            print("beam intensity attenuated by %f" % self.att_factor)
        else:
            factor=a
            mov([atn1x, atn2x, atn3x],[2.09,-1.83, -4.25])     
            print("full beam")
            self.att_factor=100
            
#Attn= Attenuator()
