print(f"Loading {__file__}...")

# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

from epics import PV
import time

NO_PARAMETERS = "__EMPTY__"

class MethodPV(PV):
	def execute(self,*args):        
		if len(args)==0:
			pars = [NO_PARAMETERS,]
		else:
			pars=[]
			for arg in args:
				pars.append(str(arg))
        
		#Python implementation does not support writing a an array if return is a single value
		if (len(pars)>1):
			self.put(pars,wait=True) 
			ret = self.get(use_monitor=False)[0]
		else:
			self.put(pars[0],wait=True)      
			ret = self.get(use_monitor=False)
                
		if self.severity!=0:
			raise Exception(ret)
		return ret  
        
        
################################################
#Sincronizing Activities
################################################

def waitReady(timeout=-1):    
	state = PV("SW:State")
	start = time.perf_counter()
	while True:
		if state.get() not in ("Running","Moving","Busy","Initialize"):
			break
		if (timeout>=0) and ((time.perf_counter() - start) > timeout):
			raise Exception("Timeout waiting ready")
		time.sleep(0.01)

def isTaskRunning(id):    
	pv = MethodPV("SW:isTaskRunning")
	return pv.execute(id)
    


def getTaskReturn():
	smpStat = []
	stat,exception = PV("SW:LastTaskInfo").get()[4:6]
	if stat.startswith("ABORT"):
		stat,exception  = stat.split(": ")
        
	if stat.startswith("Done") and stat.find("/")>=0:
		stat,tmp = stat.split(" ")
		smpStat  = [s=="True" for s in tmp.split("/")]
        
	if stat not in ("Done", "ABORT") and exception not in ("", "null"):
		stat = "ABORT"
	return stat,smpStat,exception


def getParameter(par):
	par_get = MethodPV("SW:getRobotVariable")
	return par_get.execute(par)

def setParameter(parName,parVal):
	par_set = MethodPV("SW:setRobotVariable")
	par_set.execute("nDummy",-1)
	getParameter("nDummy")
	par_set.execute(parName,parVal)
	if parVal!=float(getParameter(parName)):
		raise Exception("Failed to set parameter "+str(parName))
	return True


def runATask(cmd="Test",timeout=-1):
	task = MethodPV("SW:startRobotTask")
	taskid =  task.execute(cmd, timeout)
	print("Running Task", cmd.upper(), isTaskRunning(taskid))
	waitReady(timeout)
	print("Task", cmd.upper(), "isRunning = ", isTaskRunning(taskid))
	return getTaskReturn()


class EM_Sol_Robot():
	
	CMD_TIMEOUT = 500000

	def rebootEMBL(self):
		abort = MethodPV("SW:abort")
		restart = MethodPV("SW:restart")
		abort.execute()
		restart.execute()

	def runTask(self,cmd,timeout):
		cmdLists = ['Load', 'Mount', 'Unmount', 'Unload', 
                'Initialize', 'PowerOff', 'Home', 'Push', 'Idle','Park',
                'OpenStorageDoor', 'ShutStorageDoor', 'OpenGripper', 'CloseGripper']
		if cmd not in cmdLists:
			raise Exception(cmd+" is not a valid Task.")

		return runATask(cmd,timeout)
                #result = runATask(cmd,timeout)
                #print(result)
		#return result

	def powerOn(self):
		self.runTask('Initialize', self.CMD_TIMEOUT)

	def powerOff(self):
		self.runTask('PowerOff', self.CMD_TIMEOUT)

	def openGripper(self):
		self.runTask('OpenGripper', self.CMD_TIMEOUT)

	def closeGripper(self):
		self.runTask('CloseGripper', self.CMD_TIMEOUT)

	def goHome(self):
		cmdList = ['Initialize','Home']
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

	def park(self):
		cmdList = ['Initialize','Home','Park','PowerOff']
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

	def loadTray(self,nTube):
		if nTube<1 or nTube>20:
			raise Exception("Tube position is out of range [0 ... 20]")

		setParameter("nTray", nTube)
		cmdList = ['Initialize','Load']

		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd=="Load":
				if not bPicked and not bLoaded:
					raise Exception("FATAL: Load Failed. Tray lost during loading")
				if not bPicked and bLoaded:
					raise Exception("Load Failed. Did not pick the tray")
		return


	def unloadTray(self,nTube):
		if nTube<1 or nTube>20:
			raise Exception("Tube position is out of range [0 ... 20]")

		setParameter("nTray", nTube)
		cmdList = ['Initialize','Unload']

		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd=="Unload":
				if not bLoaded:
					ret=self.push(nTube)
					if ret==False:                   
						raise Exception("FATAL: Unload Failed. Tray lost during unloading")

		return

	def mount(self):
		cmdList = ['Initialize','Mount']

		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd=="Mount":
				if not bPicked and not bMounted:
					ret=self.push(0)
					if ret==False:
						raise Exception("FATAL: Mount Failed. Tray lost during mounting")
		return

	def unmount(self):
		cmdList = ['Initialize','Unmount']

		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd=="Unmount":
				if not bPicked and not bMounted:
					raise Exception("FATAL: Unmount Failed. Tray lost during unmounting")
				if not bPicked and bMounted:
					raise Exception("Unmount Failed. Did not pick the tray")
		return

	def push(self,nTube):
		setParameter("nTray", nTube)
		tskStat, sampleStat, exception = self.runTask("Push", self.CMD_TIMEOUT)
		return True if tskStat.lower()=="done" else False
                
    
	def sleep(self):
		cmdList = ['Initialize','Home','Idle']
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)



rbt = EM_Sol_Robot()

def testRobot(sMode='A',nbgn=1,nend=20,nloop=1):
  if sMode not in ['A','B','C','D','E'] or nloop<1:
    raise Exception("Parameter Error")

  rbt.powerOn()

  for n in range(1,nloop+1):
    for nTray in range(nbgn,nend+1):
      setParameter("nTray", nTray)

      if sMode=='A':
        rbt.loadTray(nTray)
        rbt.unloadTray(nTray)
        
      elif sMode=='B':
        rbt.loadTray(nTray)
        rbt.mount()
        rbt.unmount()
        rbt.unloadTray(nTray)
         
      elif sMode=='C':
        rbt.loadTray(nTray)
        if nTray==20:
          rbt.unloadTray(1)
        else:
          rbt.unloadTray(nTray+1)
        
      elif sMode=='E':
        rbt.loadTray(nTray)
        rbt.mount()
        sol.select_tube_pos(0)
        time.sleep(2)
        sol.select_tube_pos('park')
        rbt.unmount()
        rbt.unloadTray(nTray)
        
      else:
        rbt.loadTray(nTray)
        rbt.mount()
        rbt.unmount()
        if nTray==20:
          rbt.unloadTray(1)
        else:
          rbt.unloadTray(nTray+1)

         


