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


class EM_Robot():

	CMD_TIMEOUT = 500000

	def resetHeartBeat(self):
		setParameter("nDummy", 882)

	def rebootEMBL(self):
		abort = MethodPV("SW:abort")
		restart = MethodPV("SW:restart")
		abort.execute()
		restart.execute()

	def runTask(self,cmd,timeout):
		cmdLists = ['LoadTray', 'MountTray', 'UnmountTray', 'UnloadTray',
                'LoadPlate', 'MountPlate', 'UnmountPlate', 'UnloadPlate',
                'LoadBead', 'MountBead', 'UnmountBead', 'UnloadBead',
                'Initialize', 'PowerOff', 'Home', 'Idle','Park',
                'OpenGripper', 'CloseGripper','TraceSample','resetSoftIO']
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

	def resetSoftIO(self):
                self.runTask('resetSoftIO', self.CMD_TIMEOUT)

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

	def __load(self,sType,n,cmdList):
		ranges={"Tray":range(1,21), "Plate":range(1,9), "Bead":range(1,8)}
		if n not in  ranges[sType]:
                	raise Exception(sType+" position is out of range ["+ranges[sType][0]+" ... "+ranges[sType][-1]+"]")

		setParameter("nSample", n)
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd==cmdList[-1]:
				if not bPicked and not bLoaded:
					raise Exception("FATAL: Load Failed. "+sType+" lost during loading")
				if not bPicked and bLoaded:
 					raise Exception("Load Failed. Did not pick "+sType+" "+n)
		return tskStat, sampleStat


	def loadTray(self,nTray):
 		cmdList = ['Initialize','LoadTray']
 		return self.__load("Tray",nTray,cmdList)

	def loadPlate(self,nPlate):
 		cmdList = ['Initialize','LoadPlate','TraceSample']
 		return self.__load("Plate",nPlate,cmdList)

	def loadBead(self,nBead):
		cmdList = ['Initialize','LoadBead','TraceSample']
		return self.__load("Bead",nBead,cmdList)


	def __unload(self, sType, n, cmdList):
		ranges={"Tray":range(1,21), "Plate":range(1,9), "Bead":range(1,8)}
		if n not in  ranges[sType]:
			raise Exception(sType+" position is out of range ["+ranges[sType][0]+" ... "+ranges[sType][-1]+"]")

		setParameter("nSample", n)
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd==cmdList[-1]:
				if not bLoaded:
					raise Exception("FATAL: Unload Failed. "+sType+" lost during unloading")
		return tskStat, sampleStat


	def unloadTray(self,nTray):
		cmdList = ['Initialize','UnloadTray']
		return self.__unload("Tray",nTray,cmdList)

	def unloadPlate(self,nPlate):
		cmdList = ['Initialize','UnloadPlate','TraceSample']
		return self.__unload("Plate",nPlate,cmdList)

	def unloadBead(self,nBead):
		cmdList = ['Initialize','UnloadBead','TraceSample']
		return self.__unload("Bead",nBead,cmdList)


	def __mount(self, sType, cmdList):
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd==cmdList[-1]:
				if not bPicked and not bMounted:
					raise Exception("FATAL: Mount Failed. "+sType+" lost during mounting")
		return tskStat, sampleStat

	def mountTray(self):
		cmdList = ['Initialize','MountTray']
		return self.__mount("Tray",cmdList)

	def mountPlate(self):
		cmdList = ['Initialize','MountPlate','TraceSample']
		return self.__mount("Plate",cmdList)

	def mountBead(self):
		cmdList = ['Initialize','MountBead','TraceSample']
		return self.__mount("Bead",cmdList)


	def __unmount(self, sType, cmdList):
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)

			if len(sampleStat)==3:
				[bMounted,bPicked,bLoaded]  = sampleStat

			if cmd==cmdList[-1]:
				if not bPicked and not bMounted:
					raise Exception("FATAL: Unmount Failed. "+sType+" lost during unmounting")
				if not bPicked and bMounted:
					raise Exception("Unmount Failed. Did not pick the "+sType+" "+n)
		return tskStat, sampleStat

	def unmountTray(self):
		cmdList = ['Initialize','UnmountTray']
		return self.__mount("Tray",cmdList)

	def unmountPlate(self):
		cmdList = ['Initialize','UnmountPlate','TraceSample']
		return self.__mount("Plate",cmdList)

	def unmountBead(self):
		cmdList = ['Initialize','UnmountBead','TraceSample']
		return self.__mount("Bead",cmdList)


	def sleep(self):
		cmdList = ['Initialize','Home','Idle']
		for cmd in cmdList:
			tskStat, sampleStat, exception = self.runTask(cmd, self.CMD_TIMEOUT)
			if (tskStat.lower()!="done"):
				raise Exception(cmd+" "+tskStat+" with exception "+exception)



rbt = EM_Robot()

def testRobot(sMode='A',nbgn=21,nend=24,nloop=1):
  if sMode not in ['A','B','C','D','E','F'] or nloop<1:
    raise Exception("Parameter Error")

  EMconfig = PV("XF:16IDC-ES:EMconfig").get()
  types = {0:"Tray", 1:"Plate", 2:"Bead"}
  maxSamples = {"Tray":20, "Plate":8, "Bead":7}
  load = getattr(rbt,'load'+types[EMconfig])
  mount= getattr(rbt,'mount'+types[EMconfig])
  unmount= getattr(rbt,'unmount'+types[EMconfig])
  unload = getattr(rbt,'unload'+types[EMconfig])

  rbt.powerOn()

  for n in range(1,nloop+1):
    for nSample in range(nbgn,nend+1):
      setParameter("nSample", nSample)

      if sMode=='A':
        load(nSample)
        unload(nSample)

      elif sMode=='B':
        load(nSample)
        mount()
        unmount()
        unload(nSample)

      elif sMode=='C':
        load(nSample)
        if nSample==maxSamples[types[EMconfig]]:
          unload(1)
        else:
          unload(nSample+1)

      elif sMode=='E':
        load(nSample)
        mount()
        move_sample(0)
        time.sleep(2)
        move_sample("park" if EMconfig==0 else 'park fixed')
        unmount()
        unload(nSample)

      else:
        load(nSample)
        mount()
        unmount()
        if nSample==maxSamples[types[EMconfig]]:
          unload(1)
        else:
          unload(nSample+1)




