#!/opt/conda_envs/collection-17Q2.0/bin/ipython --profile=collection
###!/opt/conda_envs/lsdcLix3_1/bin/ipython -i
###!/usr/bin/python -Wignore
#from __future__ import (absolute_import, division, print_function,unicode_literals)
lsdcSupport = 1
try:
  import string
  import sys
  import os
  import time
  import _thread
  import db_lib
  import daq_macros
#from daq_macros import *
  import daq_lib
  from daq_lib import *
  import daq_utils
#from robot_lib import *
  import det_lib
  import beamline_support
  import beamline_lib
  from beamline_lib import *
#import stateModule
  import atexit
  import super_state_machine
except ModuleNotFoundError:
  lsdcSupport = 0
  
#from bluesky.global_state import gs
sitefilename = ""
global command_list,immediate_command_list,z,abort_flag
command_list = []
immediate_command_list = []
z = 25
abort_flag = 0



global ssem
ssem = None


def measure(tn, nd=None, vol=50, exp=5, repeats=3, sample_name='test', delay=0):
  global ssem
  if (ssem == None):
    ssem = SolutionScatteringExperimentalModule()
  ssem.measure(tn, nd, vol, exp, repeats, sample_name, delay)
  
def lixAbortBS():
  print("enter abortBS")  
#  RE = gs.RE
  print("trying to abort")
  print(RE.state)
  if (RE.state != "idle"):
    try:
      RE.abort()
    except super_state_machine.errors.TransitionError:
      print("caught BS")

            

def stopDCQueue(flag):
  print("stopping queue in daq server " + str(flag))
  abort_data_collection(int(flag))

def abort_data_collection(flag):
  global datafile_name,abort_flag,image_started

  print("enter abort dc")
  if (flag==2): #stop queue after current collection
    abort_flag = 2
    return
#  if (1):   #for now
#    beamline_lib.bl_stop_motors() ##this already sets abort flag to 1
  abort_flag = 1
#  gon_stop() #this calls osc abort
  time.sleep(2)
#  detector_stop()
  print("calling abortBS")
  lixAbortBS()


def runDCQueue(): #maybe don't run rasters from here???
  global abort_flag

  autoMounted = 0 #this means the mount was performed from a runQueue, as opposed to a manual mount button push
  print("running queue in daq server")
  while (1):
    if (abort_flag):
      abort_flag =  0 #careful about when to reset this
      return
    currentRequest = db_lib.popNextRequest(daq_utils.beamline)
    print(currentRequest)
    if (currentRequest == {}):
      break
    db_lib.updatePriority(currentRequest["uid"],99999)
    refreshGuiTree()     
    collectData(currentRequest)
    db_lib.updatePriority(currentRequest["uid"],-1)
    refreshGuiTree()     
  return


def collectData(currentRequest):
  global data_directory_name

#  print(currentRequest)
#  print("pretending to collect")
#  time.sleep(5)
#  db_lib.updatePriority(currentRequest["uid"],-1)
#  refreshGuiTree()
#  return 1 #SHORT CIRCUIT

  reqObj = currentRequest["request_obj"]
#  logMxRequestParams(currentRequest)  
  sampID = reqObj["sample"]
  data_directory_name = str(reqObj["directory"])
  file_prefix = str(reqObj["file_prefix"])
  prot = str(reqObj["protocol"])    
  sampleName = db_lib.getSampleNamebyID(sampID)
#  if not (os.path.isdir(data_directory_name)):
#    comm_s = "mkdir -p " + data_directory_name
#    os.system(comm_s)
#    comm_s = "chmod 777 " + data_directory_name
#    os.system(comm_s)
  if (prot == "SolScatter"):  
    (tubePos,tubeNumber,tubeID) = db_lib.getCoordsfromSampleID("lix",sampID)
    delay = reqObj["delay"]
    exposure_time = reqObj["exposure_time"]
    needlePos = reqObj["needlePos"]
    repeats = reqObj["repeats"]
    volume = reqObj["volume"]
    comm_s = "measure(" + str(tubeNumber+1) + "," + needlePos + "," + str(volume) + "," + str(exposure_time) + "," + str(repeats) + "," + sampleName + "," + str(delay) + ")"
    print(comm_s)
    print("before measure")
    measure(tubeNumber+1,needlePos,volume,exposure_time,repeats,sampleName,delay)
    print("after measure")    




def pybass_init():
  global message_string_pv

#  db_lib.db_connect()
  daq_utils.init_environment()
  init_var_channels()
#  init_diffractometer()
  det_lib.init_detector()  
  daq_lib.message_string_pv = beamline_support.pvCreate(daq_utils.beamlineComm + "message_string")    
  daq_lib.gui_popup_message_string_pv = beamline_support.pvCreate(daq_utils.beamlineComm + "gui_popup_message_string")    
  if (1):
#  if (daq_lib.has_beamline): # for now
#    try:
    beamline_lib.read_db()
    print("init mots")
#      beamline_support.init_motors()
    init_mots()    #for now
    print("init done mots")
    init_diffractometer()
#      init_counters() #for now
#      newfile("scandata")
##    except CaChannelException as status:
##      print(ca.message(status))
##      gui_message("EPICS motor Initialization Error. Exit and try again. If problem persists, EPICS may need to be restarted.")


if (lsdcSupport):
  pybass_init()
