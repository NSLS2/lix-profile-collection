print(f"Loading {__file__}...")
##APV device file is loaded into bsui and instantiates APV class
'''
##STeps to complete a purge
1) Select port to purge on APV valve (its always connected to channel A)
2) Open the Agilent purge valve, check pressure
3) INcrease flow rate and set timer
4) Select the column purge valve to clear superloop (Col1 or Col2) and set to waste.
5) Check pressure
6) Lower flow rate to 1ml/min
6) Close Agilent Purge Valve
8) Set timer
9)Check column type, set pressure limit, lower flow rate to column flow rate
10) Close column purge valve
11) Begin equilibration
'''
from time import sleep

def select_buffer_channel(pos=1):
    APV.movePosition(position=pos)
    print(f"Selecting buffer channel {pos} to purge")
    

def open_pump_purge_valve(valve, valve_ID=2, get_ret=False):
    print("Check that Agilent buffer line is set to A, buffer channel is correct (1-6) and that proper pressure limits are set!")
    #ret=VV.check_valve_pos(ID=2)
    #print(ret)
    VV.send_valve_cmd(cmd="GO", valve=VICI_ID.Agilent_purge, valve_ID=2, get_ret=get_ret)
    print(f"Purging Quaternary Pump with Valve {valve_ID}.  Set flowrate in Agilent software")
    VV.check_valve_pos(valve = valve, valve_ID=2)

def close_purge_pump(valve=VICI_ID.Agilent_purge, valve_ID=2, get_ret=False):
    print("Adjust flowrate in agilent software to proper limit (0.35ml/min) and that proper pressure limits are set!")
    #ret=VV.check_valve_pos(ID=2)
    #print(ret)
    VV.send_valve_cmd(cmd="GO", valve=valve, valve_ID=2, get_ret=get_ret)
    print(f"Purge pump closed with Valve {valve_ID}.")
    VV.check_valve_pos(valve=valve, valve_ID=2)

def purge_superloop_open(valve=VICI_ID.Col1_purge,flowrate=2, valve_ID=3,get_ret=False):
    print("Check pressure limits and do not exceed 2mL/min")
    if flowrate > 2:
        raise Exception("Agilent Superloop flowrate exceeded")
    else:
        #VV.send_valve_cmd(cmd="CP", ID=3)
        VV.send_valve_cmd(cmd="GO", valve=valve, valve_ID=3, get_ret=get_ret)
        VV.check_valve_pos(ID=3)
    print("Purging superloop")

def purge_superloop_close(valve=VICI_ID.Col1_purge, valve_ID=3, get_ret=False):
    print("Check pressure limits and set flowrate in agilent software to 0.35mL/min")
    #VV.send_valve_cmd(cmd="CP", ID=3)
    VV.send_valve_cmd(cmd="GO", ID=3, get_ret=get_ret)
    VV.check_valve_pos(ID=3)
    print("Purging superloop completed")


def purge_method(pos=1):
    '''
    Buffer position must be between 1-6
    '''
    input("Please ensure you selected the correct buffer line! Then hit enter:")
    ##check pump pressure here before proceeding
    ##check pump flowrate
    print(caget('XF:16IDC-ES{HPLC}QUAT_PUMP:FLOWRATE_RBV'))
    ##set pump flow rate low
    open_purge_pump()
    ##check pressure here and perform a try loop
    ##if pressure is OK then set flowrate 2mL/min
    #input("Set Agilent pump to 1mL/min, then hit enter:")
    for i in range(180,0,-1):
        print(f"{i} seconds remaining...", end="\r")
        time.sleep(1)
    ##check pressure
    ##set flowrate to 1mL/min
    input("After purging pump, set flow rate to <2mL/min to purge superloop, then hit enter:")
    purge_superloop_open()
    time.sleep(2)
    close_purge_pump()
    #time.sleep(20)
    for i in range(120,0,-1):
        print(f"{i} seconds_remaining...", end="\r")
        time.sleep(1)
    ##change flowrate
    ##check pressure
    input("Please adjust flowrate to columntype, then hit enter:")
    purge_superloop_close()


"""
Need to wash flow cell or remove air:
TRP.start_pump()
TRP.stop_pump()
TRP.set_flowrate(0.1)

"""

# # to run HPLC:

# run_hplc_from_spreadsheet("HPLC_sep_29_Watkins.xlsx", batchID="a1", exp=2)

###Processing:
'''
Need to manually move *E.CSV from Windows Results folder to your working directory
Then you can process and attach UV 280.
'''

"""
Purge steps:
1)open_purge_pump()
2)purge_superloop_open()
3)close_purge_pump()
4)purge_superloop_close()
"""
