##APV device file is loaded into bsui and instantiates APV class
import time
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


def select_buffer_channel(pos=1):
    APV.movePosition(position=pos)
    print(f"Selecting buffer channel {pos} to purge")
    
def open_pump_purge_valve(valve_ID=2, get_ret=True):
    #check agilent pump presssure
    print("Check that buffer line is correct (1-6) and that proper pressure limits are set!")
    purge_pos = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS_RBV')
    print(f"This is the first {purge_pos}")
    if purge_pos == "Open":
        print("Purge Valve for Quaternary Pump is Open")
    else:
        caput('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS' , 1)
        purge_pos = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS_RBV')
        if purge_pos == "Closed":
            raise Exception(f"Purge position for Quaternary pump is still {purge_pos}! Check that valve is calibrated.")
    print(f"Purging Quaternary Pump with Valve {ID}.  Set flowrate in Agilent software")
    return purge_pos
    
def close_purge_pump(ID=2, get_ret=False):
    print("Adjust flowrate in agilent software to proper limit for column type and that proper pressure limits are set!")
    purge_pos = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS_RBV')
    if purge_pos == "Open":
        caput('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS' , 0)
        purge_pos = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PURGE_VALVE_POS_RBV')
        if purge_pos == "Open":
            raise Exception(f"Purge valve is still {purge_pos}")
    else:
        print(f"Purge valve is {purge_pos}")
    
    return purge_pos   
        
        


def purge_superloop_open(flowrate=2, get_ret=False):
    print("Check pressure limits and do not exceed 2mL/min")
    if flowrate > 2:
        raise Exception("Agilent Superloop flowrate exceeded")
    else:
        #VV.send_valve_cmd(cmd="CP", ID=3)
        VV.send_valve_cmd(cmd="GOB", ID=3, get_ret=get_ret)
        VV.check_valve_pos(ID=3)
    print("Purging superloop")
    
def purge_superloop_close(get_ret=False):
    print("Check pressure limits and set flowrate in agilent software to 0.35mL/min")
    #VV.send_valve_cmd(cmd="CP", ID=3)
    VV.send_valve_cmd(cmd="GOA", ID=3, get_ret=get_ret)
    VV.check_valve_pos(ID=3)
    print("Purging superloop completed")
    
    
    

"""
Need to wash flow cell or remove air:
TRP.start_pump()
TRP.stop_pump()
TRP.set_flowrate(0.1)

"""

## to run HPLC:

#run_hplc_from_spreadsheet("HPLC_sep_29_Watkins.xlsx", batchID="a1", exp=2)

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
