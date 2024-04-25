""" config for 2023-1, new sample handler, separate static and HPLC flow cells
"""
#!/usr/bin/python3
import socket
import numpy as np
from time import sleep
import signal
import itertools


# cell 2 tested
sol = SolutionScatteringExperimentalModule(camName="camES2")
sol.cam.setup_watch("upstream", "stats1.total", 0.15e5, base_value=1.3e5)#8.6 came out 5.5
sol.cam.setup_watch("downstream", "stats1.total", 0.15e5, base_value=1.15e5)#7.7 came out 4.4
#cell 1
'''
sol.cam.setup_watch("upstream", "stats1.total", 0.15e5, base_value=3.05e5)#3.2,8.6 came out 5.5
sol.cam.setup_watch("downstream", "stats1.total", 0.15e5, base_value=3.05e5)#,2.77.7 came out 4.4 0.35change


sol = SolutionScatteringExperimentalModule(camName="camES1")

sol.cam.setup_watch("upstream", "stats1.total", 0.1e7, base_value=6.7e7)
sol.cam.setup_watch("downstream", "stats1.total", 0.1e7, base_value=7.58e5)
'''

#sol.tctrl = tctrl_FTC100D(("xf16idc-tsvr-sol", 4001))
sol.tctrl = tctrl_FTC100D(("xf16idc-tsvr-sena", 7002)) # use this

sol.vol_sample_headroom = 5
sol.drain_duration = 2
sol.wash_duration = 0.4
sol.default_wash_repeats = 2
sol.default_dry_time = 25
sol.delay_before_release = 0.2
sol.ctrl.water_pump_spd.put(1)
sol.default_piston_pos = 90
sol.default_load_pump_speed = 1300
sol.default_pump_speed = 750 #1000

# need to define positions for ss.z, ss.xc

sol.vol_p4_to_cell = {'upstream': -80, 'downstream': -80}
sol.vol_tube_to_cell = {'upstream':100,'downstream':102}
# u -80 d -80
# u 150, d 145

sol.flowcell_pos = {'bottom': [-8.45, 0, 6.23], #[-7.53, 0, 5.8] #cell 2 position
                    'top':    [-8, 0, 1.31], #[-7.53, 0, 0.8] #cell 2 position
                    'middle': [41.55, 0, 4.42],
                    'scint':    [ 19,0, -0.5],
                    'empty':  [ 9.47, 0, 4.8],
                    'std':  [ 23.27, 0, -0.5]}  ##23.47 scintillator switched & 19.27

sol.cam.watch_timeouts_limit = 10      # default is 3

# cell_type: N, x0, y0, dx, dy,
# position 0 is on the inboard side
cell_formats = {'cap': [15, -42.15, 4.6, 6.35, 0],  # capillary holder
                'flat8': [8, 44.8, 4.0, 9.0, 0.06], # washable  
                'flat10UIUC': [10, 78.1, 14.5, 9.432, 0], 
                'flat15': [15, 58.9, 4.5, 6.35, 0.0725], # Northwestern
                'std': [3, 29.6, 3.0, 20, 0], # std samples mounted on flat15
               }

sol.sample_format_dict = {}
for k in cell_formats.keys():
    N,x0,y0,dx,dy = cell_formats[k]
    sol.sample_format_dict[k] = fixed_cell_format(cell_type=k, Npos=N,
                                               motor_position1={'xc': x0, 'y': y0},
                                               offset={'xc': dx, 'y': dy}
                                              )        

