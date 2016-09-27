#!/opt/conda/bin/python3
import socket, time
import numpy as np
from threading import Timer

class Serial_device:
  def __init__(self, sock_addr):
    self.delay = 0.2
    self.sock = socket.create_connection(sock_addr)

  def comm(self, cmd, get_ret=True):
    self.sock.send(cmd.encode())
    if get_ret:
      time.sleep(self.delay)
      ret = self.sock.recv(256).decode('utf8','ignore')
      return ret

  def set_delay(self, t):
    self.delay = t


# this defines the SC5 solenoid driver
class SC5(Serial_device):
  def __init__(self, sock_addr):
    super().__init__(sock_addr) 

  def read(self, ch):
    ret = self.comm("Q\r")
    if ch<0 or ch>4:
      print("invalid channel number: %d (must be between 0 and 4)" % ch)
      print("SC5 state = %s" % ret)
      return 
    self.state = np.asarray(ret.strip("Q\r").split(","), np.int)
    return self.state[ch]    

  def set(self, ch, st):
    if ch<0 or ch>4:
      print("invalid channel number: %d (must be between 0 and 4)" % ch)
      return
    if st!=0: st=1
    self.comm("S%d,%d\r" % (ch,st))
    self.read(ch)

  # this turns on a channel for t_on then turn it off
  def set_timed_on(self, ch, t_on):
    self.set(ch, 1)
    Timer(t_on, self.set, (ch, 0)).start()

# this defines a syringe pump
### highest motor speed is 10000/s, lowest is 60/s
### conversion factor is 1000ul / 48000steps
### so maximum speed is 208ul/s, or 12500ul/min
### limit to 50ul/s, or 1800ul/min
### minimum speed is 0.83ul/s, or 50ul/min
class versa6(Serial_device):
  def __init__(self, sock_addr, vol, max_motor_spd=10000, min_motor_spd=60, N_valve_ports=3):
    super().__init__(sock_addr) 
    self.max_vol = vol                      # syringe volume in ul
    self.cv_factor = 48000/vol		    # 24000 steps = 1000ul ???
    # motor speed is in steps/sec
    # pump speed is in uL/min
    self.max_motor_spd = max_motor_spd
    self.min_motor_spd = min_motor_spd
    self.max_spd = np.max([2000, max_motor_spd*60./self.cv_factor])
    self.min_spd = min_motor_spd*60./self.cv_factor
    self.cur_motor_spd = -1
    self.N_valve_ports = N_valve_ports

  def wait(self):
    while True:
      ret = self.comm("/1\r")
      print("checking pump ... : status=%s  \r" % ret[:3], end="")
      if ret[:3]=="/0`": break
      time.sleep(1)   
    print("\n")

  def reset(self):
    print(self.comm("/1Y4R\r"))
    self.wait()
  
  # position in ul
  def mvA(self, vol):
    _pos = vol*self.cv_factor
    if _pos<0 or _pos>48000: 			# out of range
      print("pump out of range. better check.")
      exit
    print("moving pump to %d (steps) / %.1f (uL)\n" % (_pos, vol))

    self.comm("/1A%dR\r" % _pos)
    self.comm("/1\r")

  def umvA(self, vol):
    self.mvA(vol)
    self.wait()

  def mvR(self, dv):
    self.wait()	# just in case the pump is busy
    # get current position first
    ret = self.comm("/1?\r")
    _pos0 = np.int(ret[3:-3])  # return looks like this: '/0`2880 \x03\r\n'
    vol0 = _pos0/self.cv_factor
    print("current pump position is %d (steps) / %.1f (uL)" % (_pos0, vol0))
    # calculate new position (ul)
    _dp = dv*self.cv_factor;
    print("pump_mvR: %f (steps) / %f.1 (uL)\n" % (_dp,dv))
    self.mvA(vol0+dv)

  def umvR(self, dv):
    self.mvR(dv)
    self.wait()

  def get_motor_speed(self):
    ret = self.comm("/1?2\r")  # return looks like this: '/0`5000 \x03\r\n'
    return np.int(ret[3:-3])  

  def set_motor_speed(self, motor_spd):
    while (True):
      ret = self.comm("/1V%d\r" % motor_spd)
      self.wait()
      av = self.get_motor_speed()
      if np.fabs(av-motor_spd)<0.05*motor_spd: break
      printf("pump_set_speed failed. requested:%.1f, actual:%.1f" % (vel, av*60/self.cv_factor))
      printf("retry ...");
      time.sleep(2)
    return av

  def get_speed(self):
    return self.get_motor_speed()*60/self.cv_factor

  def restore_speed(self):
    self.wait() # in case pump is still moving
    self.set_motor_speed(self.cur_motor_spd)
    # set backlash back
    sock_put(SOCK_SYRINGE_PUMP,"/1K200R\r")

  def set_speed(self, vel):
    motor_spd = vel*self.cv_factor/60
    if motor_spd>self.max_motor_spd or motor_spd<self.min_motor_spd: 
      print("pump speed must in the range of %.1f-%.1f ul/min\n" % (self.min_spd, self.max_spd))
      return
    av = self.set_motor_speed(motor_spd)
    print("pump speed (uL/min): requested:%.1f, actual:%.1f" % (vel, av*60/self.cv_factor))

  def slow_move(self, Dt, Dv):
    #print("pump_slow_move: vol=%f, tt=%f\n" & (dv,dt))  
    # slowest pump speed is PUMP_MIN_MOTOR_SPEED*60/pump_cv_factor
    spd = np.fabs(Dv)/Dt*60
    self.cur_motor_spd = self.get_motor_speed()
    if spd >= self.min_spd:
      self.set_speed(spd)
      self.mvR(Dv)
    else: # use program
      # set backlash to zero.
      self.comm("/1K0R\r")
      # the manual (page 70) says moving one step takes 24ms, not sure why
      # also not sure how the Top Speed affect this time
      self.set_motor_speed(self.min_motor_spd)
      tstep = 1./self.min_motor_spd
      # 1 step takes tstep (ms), and dispenses 1/cv_factor (ul)
      # need to insert a delay of dt(ms) to achieve the speed of vol/tt  
      rep = np.fabs(Dv)*self.cv_factor
      ## 1.1 is a scaling factor to make sure that the slow move takes enough time
      ## may or may not be necessary
      #dt = (tt/rep*1000-tstep)*PUMP_SLOW_MOVE_SCALE_FACTOR
      dt = int(Dt*1000/rep-tstep+0.5)
      # from the Versa pump manual
      # 	/1 	     address
      # 	g  	     start of a loop
      # 	D1 or P1     dispense/aspirate for 1 step (16ms, ~1/60s)
      # 	Mn 	     delay n ms
      # 	Gm 	     repeat for m times
      if Dv>0: # aspirate  
        self.comm("/1gP1M%dG%dR\r" % (dt,rep))
      else:    # dispense
        self.comm("/1gD1M%dG%dR\r" % (dt,rep)) 

  def get_valve(self):
    ret = self.comm("/1?8\r") # return looks like this: '/0`3 \x03\r\n'
    return np.int(ret[3:-3])

  def set_valve(self, vv):
    if vv<1 or vv>self.N_valve_ports:
      print("invalid valve position: %d" % vv)
      return

    while True:
      self.comm("/1o%dR\r" % vv)
      self.wait()
      sv = self.get_valve()
      if sv==vv: break
      print("error setting selection valve. requested pos#%d, actual pos#%d\n" % (vv,sv))
      ret = self.comm("/1$\r")
      print("valve stall query returns: %s\n" % ret)
      time.sleep(2)
      print("retry ...")
    return

# VICI valve
class VICI(Serial_device):
  def __init__(self, sock_addr):
    super().__init__(sock_addr) 

  def set(self, pos):
    if pos!=0: pos=1
    print("moving VICI valve: ")
    # communication problem to get back position, set blindly for now
    self.comm("GO%c\r" % chr(ord("A")+pos), get_ret=False)
    print(self.comm("CP\r"))
#    while True: 
#      self.comm("GO%c\r" % chr(ord("A")+pos), get_ret=False)
#      if self.get()==pos: break
#      print("unsuccessful attempt to move VICI valve")
#      time.sleep(1)
#      print("re-try ...")

  def get(self): 
    ret = self.comm("CP\r") # return looks like this: 'Position is B\r'
    return ord(ret[-2])-ord("A")
      

# port #3 on NPort 5410
# baud rate 9600, 8N1, no flow control
HT4PORT_SOCK=("10.16.2.58", 4003)
# position A (0):
# position B (1):

# port 1: wash/dry
# port 2: 
# port 3: syringe pump
# port 4: botom cell
# position 0: 1 connected to 4, 2 connected to 3
# position 1: 1 connected to 2, 3 connected to 4

HT_SC5_SOCKA=("10.16.2.58", 4004)
SC5_Wat = 0
SC5_Sel = 1
SC5_Sel_Wat = 0
SC5_Sel_N2 = 1
SC5_N2 = 2
SC5_Drain1 = 3
SC5_Drain2 = 4
HT_SC5_SOCKB=("10.16.2.58", 4002)
SC5_SH = 3
SC5_SD = 2
SC5_LD = 4




SOCK_SYRINGE_PUMP=("10.16.2.58",4001)	  # 2nd port on MOXA
# 3-way valve, valid positions are 1-3 (A-C)
# A: open
# B: water tank
# C: sample
PUMP_VALVE_SAMPLE=3
PUMP_VALVE_TANK=2

# set the PWM duty cycles 
def HTSC5_init(): 
  sc5B = SC5(HT_SC5_SOCKB) 
  sc5A = SC5(HT_SC5_SOCKA) 
  # default solenoid parameters are 256,250,64
  # the parameters are peak_level, peak_duration; hold_level
  # continuous power for the diaphragm pump
  print("setting diaphragm pump driver parameters: ") 
  print(sc5A.comm("P%d,128,2,2\r" % SC5_Wat))

  # selection valve is rated for 12V, supply is 24V
  # set peak level to 50% and hold level to 
  print("setting selection valve driver parameters: ") 
  print(sc5A.comm("P%d,128,128,32\r" % SC5_Sel))

  # set the other drivers to default settings
  print("setting other drivers to default parameters:")
  print(sc5A.comm("P%d,256,250,64\r" % SC5_N2))
  print(sc5A.comm("P%d,256,250,64\r" % SC5_Drain1))
  print(sc5A.comm("P%d,256,250,64\r" % SC5_Drain2))
  print(sc5B.comm("P%d,256,250,64\r" % SC5_SH))
  # write parameters to the flash memory
  print(sc5A.comm("W\r"))
  print(sc5B.comm("W\r"))
  return sc5A, sc5B

def init_syringe():
    global pp
    global vc
    global sc1
    global sc2

    try:
        pp = versa6(SOCK_SYRINGE_PUMP, 250)
        vc = VICI(HT4PORT_SOCK)
        sc1,sc2 = HTSC5_init()
    except:
        print("********* Error initializing Syringe Pump *********")

def close_syring():
    global pp
    global vc
    global sc1
    global sc2
    
    try:
        pp.sock.close()
        vc.sock.close()
        sc1.sock.close()
        sc2.sock.close()
    except:
        print("*********** Error closing Syringe Pump *************")
        
pp = None
vc = None
sc1 = None
sc2 = None
