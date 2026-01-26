""" config for 2023-1, new sample handler, separate static and HPLC flow cells
"""
#!/usr/bin/python3
import socket
import numpy as np
from time import sleep
import signal
import itertools

pil.reset_file_number = False

# initialize camBHutch as camqr for mail-in measurements
camqr = setup_cam('camBHutch')


# cell 2 IRtested
sol = SolutionScatteringExperimentalModule(camName="camIR")
sol.cam.cam.acquire_time.put(0.001)
sol.cam.cam.gain.put(5)
sol.cam.setup_watch("upstream", "stats4.total", 1e6, base_value=1.1e6)#7.1,8.6 came out 5.5
sol.cam.setup_watch("downstream", "stats4.total", 1e6, base_value=1.15e6)#6.1,7.7 came out 4.4

#cell 2 ES2
'''
sol = SolutionScatteringExperimentalModule(camName="camES2")
sol.cam.setup_watch("upstream", "stats1.total", 0.25e5, base_value=1.75e5)#3.2,8.6 came out 5.5
sol.cam.setup_watch("downstream", "stats1.total", 0.25e5, base_value=1.75e5)#,2.77.7 came out 4.4 0.35change


sol = SolutionScatteringExperimentalModule(camName="camES1")

sol.cam.setup_watch("upstream", "stats1.total", 0.6e7, base_value=4.45e7)
sol.cam.setup_watch("downstream", "stats1.total", 0.1e7, base_value=3.90e4)
'''

#sol.tctrl = tctrl_FTC100D(("xf16idc-tsvr-sol", 4001))
#sol.tctrl = tctrl_FTC100D(("xf16idc-tsvr-sena", 7002)) # use this

sol.vol_sample_headroom = 5
sol.drain_duration = 2
sol.wash_duration = 0.4
sol.default_wash_repeats = 2
sol.default_dry_time = 40
sol.delay_before_release = 4
sol.ctrl.water_pump_spd.put(1)
sol.default_piston_pos = 90
sol.default_load_pump_speed = 750
sol.default_pump_speed = 750 #1000

# need to define positions for ss.z, ss.xc

sol.vol_p4_to_cell = {'upstream': -90, 'downstream': -80}
sol.vol_tube_to_cell = {'upstream':89,'downstream':93} 
# u -80 d -80
# u 150, d 145

sol.flowcell_pos = {'bottom': [-8.85, 0, 11.51], #[-7.53, 0, 5.8] #cell 2 position
                    'top':    [-8.85, 0, 6.5], #[-7.53, 0, 0.8] #cell 2 position
                    'middle': [40.3, 0, 9.25],#39.75, 0,1.56
                    'scint': [ 16.01, 0, 4.35],
                    'carbon': [20.25, 0, 4.35],
                    'empty':  [ 9.25, 0, 9.3],
                    'AgBH':  [ 23.25, 0, 4.35]}  ##23.47 scintillator switched & 19.27

sol.cam.watch_timeouts_limit = 10      # default is 3

# cell_type: N, x0, y0, dx, dy,
# position 0 is on the inboard side
cell_formats = {'cap': [15, 57.93, 9, 6.35, 0.00],  # capillary holder
                'flat8': [8, 43.6, 9, 9.0, 0.2], # washable  
                'flat10UIUC': [10, 78.1, 14.5, 9.432, 0], 
                'flat14a': [7, 58715, 4.8, 6.35, 0.2], 
                'flat14b': [7, 11.2, 4.8, 6.35, 0.2], 
                'flat14': [14, 56.6, 0.95, 6.35, 0.2],
                'flat15': [15, 57.85, 9.0, 6.35, 0.06], # Northwestern# 0.0725 angle, edited y from 2.75 to 2.5 and dy from 0 to 0.03 250715
                'AgBH': [4, 29.1, 8.0, 20, 0], # std samples mounted on flat15, pos 2 - AgBH, 3, Scintillator, 1, Carbon
               }

sol.sample_format_dict = {}
for k in cell_formats.keys():
    N,x0,y0,dx,dy = cell_formats[k]
    sol.sample_format_dict[k] = fixed_cell_format(cell_type=k, Npos=N,
                                               motor_position1={'xc': x0, 'y': y0},
                                               offset={'xc': dx, 'y': dy}
                                              )        
#keep track of where columns are loaded.  Can identify type later
SEC_col_pos = {'pos1' :True,
              'pos2' : False}