from ophyd import (EpicsSignal, Device, Component as Cpt)
import time, sys 

global sim_on

# if True, only print the request to 
sim_on=False

import time

def check_sig_status(sig, value, poll_time=0.1):
    while True:
        if sig.get()==value:
            break
        time.sleep(poll_time)
        
class MaxiGauge:
    def __init__(self, devName):
        self.pres_sig = EpicsSignal(devName+'P:Raw-I')
    
    def pressure(self):
        msg = self.pres_sig.get()
        if msg=="UNDER":
            return 1.0e-3
        elif msg=="OVER":
            return 1.1e3
        else:
            return float(msg)
                   
class MKSGauge:
    """ can read pressure, status of the gauge "OFF", "NO GAUGE"
        turn on and off
    """
    def __init__(self, devName):
        self.pres_sig = EpicsSignal(devName+'P:Raw-I')
        self.power_ctrl = EpicsSignal(devName+'Pwr-Cmd')

    def pressure(self):
        """ raise exception if the gause if not present or off
        """
        Pr = self.pres_sig.get()
        if Pr=="NO_GAUGE" or Pr=="OFF":
            raise Exception(Pr, self.pres_sig.name)
        elif Pr=="LO<E-03":
            P0 = 1.0e-3
        elif Pr==">1.0E+03":
            P0 = 1.1e3
        else:
            P0 = np.float(Pr)

        return P0                
        
    def power(self, state, max_try=10):
        """ turn the gauge on or off
        """
        if max_try<=0:
            raise Exception("could not change gauge state to ", state)
        self.power_on = self.power_ctrl.get()
        if state=="ON" or state=="on":
            if self.power_on:
                return
            else:
                self.power_ctrl.put(1)
                time.sleep(1.5)
                return self.power(state, max_try-1)
        else:
            if self.power_on:
                self.power_ctrl.put(0)
                time.sleep(1.5)
                return self.power(state, max_try-1)
            else:
                return
            
        
class SolenoidValve:
    """ this works for both gate valves and solenoid valves
        status of the valve is given by PV [deviceName]Pos-Sts
        open the valve by setting PV [deviceName]Cmd:Opn-Cmd to 1
        close the valve by setting PV [deviceName]Cmd:Cls-Cmd to 1
    """
    def __init__(self, devName):
        """ for soft pump valves devName should be a list
            some valves have 
        """
        if isinstance(devName, list): # soft pump valves
            if len(devName)!=2:
                raise Exception("2 device names must be given for a soft pump valve.")
            self.has_soft = True
            self.soft_valve = SolenoidValve(devName[1])
            devName = devName[0]
            self.devName = devName
        else:
            self.has_soft = False
            self.devName = devName
            
        self.sig_status = EpicsSignal(devName+'Pos-Sts')
        self.sig_open = EpicsSignal(devName+'Cmd:Opn-Cmd')
        self.sig_close = EpicsSignal(devName+'Cmd:Cls-Cmd')
            
    def open(self, softOpen=False):
        print("request to open valve: ", self.devName)
        if sim_on:
            print("simulation mode on, the valve state will not change.")
            return
        if softOpen and self.has_soft:
            self.close()
            self.soft_valve.open()
        else:
            if self.has_soft:
                self.soft_valve.close()
            self.sig_open.put(1)
            check_sig_status(self.sig_status, 1)
            
    def close(self):
        print("request to close valve: ", self.devName)
        if sim_on:
            return
        if self.has_soft:
            if self.soft_valve.status==1:
                self.soft_valve.close()
        if self.status==1:
            self.sig_close.put(1)
            check_sig_status(self.sig_status, 0)
        
    @property
    def status(self):
        if self.has_soft:
            return 0.5*self.soft_valve.status + self.sig_status.get()
        else:
            return self.sig_status.get()
            

class VacuumSystem:
    """ Maintain a list as the map of the vacuum system. constructed by appending vacuum sections
        Each vacuum section must have a pressure gauge, a vent valve, an evacuation valve and a downstream gate valve
        It is assumed that the vacuum system starts and ends with a window/blank
        Operations allowed:
            vent: check gate valves
            evacuate: check pump pressure
            openGV: check downstream vacuum pressure
            closeGV: just do it
        
        the endstation manifold needs to be treated separately
    """
    def __init__(self, pumpGaugeDev):
        self.pump_gauge = pumpGaugeDev
        self.VSmap = []
        self.VSindex = {}
        self.manifolds = {}
        self.numSec = 0
        self.maxAllowedPressureDiff = 0.1  # not allow to open GV if pres. diff. exceeds this value
        self.acceptablePumpPressure = 0.01 # pump pressure should be better than this during normal ops

    def pressure(self, secName='pump'):
        """ support "pump" as a secName as well
        """
        if secName=='pump':
            dev = self.pump_gauge
        else:
            dev = self.VSmap[self.VSindex[secName]]['gauge']
        return dev.pressure()
            
    def appendManifold(self, mfName, EVDevName, VVDevName):
        """ a manifold is not directly connected to a vacuum section
            but it has an evacuation valve and a vent valve
        """
        EV = SolenoidValve(EVDevName)
        VV = SolenoidValve(VVDevName)
        self.manifolds[mfName] = {"EV": EV, "VV": VV, "vacSecs": []}
        
    def findManifold(self, secName):
        """ return the name of the manifold that the vacuum section is attached to
            return None if the section is not attached to a manifold
        """
        ns = self.VSindex[secName]
        if "manifold" in list(ESVacSys.VSmap[ns].keys()):
            return self.manifolds[self.VSmap[ns]["manifold"]]
        return None
    
    def appendSection(self, secName, gaugeDev, EVName=None, VVName=None, 
                      manifoldName=None, IVName=None, downstreamGVName=None):
        """ a vacuum section must have a vacuum gauge
            it should either have a set of evacuation/vent valves
            or be attached to a manifold through a isolation valve 
            
            vacuum sections in a vacuum systems are continuous, separated by a GV
            the GV could be None, meaning the sections are effectively separated by a window
        """
        
        if downstreamGVName != None:
            GV2 = SolenoidValve(downstreamGVName)
        else:
            GV2 = None
        self.VSindex[secName] = self.numSec
        if self.numSec>0:
            GV1 = self.VSmap[self.numSec-1]["GVs"][1]
        else:
            GV1 = None
        GVs = [GV1, GV2]
                        
        if manifoldName!=None:
            if not (manifoldName in list(self.manifolds.keys())):
                raise Exception("manifold not defined: ", manifoldName)
            IV = SolenoidValve(IVName)
            self.VSmap.append({"name": secName, "IV": IV, "GVs": GVs, "gauge": gaugeDev, "manifold": manifoldName})
            # to keep track of what vacuum sections are attached to the manifold
            self.manifolds[manifoldName]["vacSecs"].append(secName)
        else:
            EV = SolenoidValve(EVName)
            VV = SolenoidValve(VVName)
            self.VSmap.append({"name": secName, "EV": EV, "VV": VV, "GVs": GVs, "gauge": gaugeDev})     
        
        self.numSec += 1
        
    def allowToOpen(self, P0, P1):
        """ allow the valve open if the pressure diffence is sufficiently small (0.05 mbar)
        """
        if np.fabs(P0-P1)<self.maxAllowedPressureDiff:
            return True
        print("pressure difference is too great to open the valve: %.3f / %.3f mbar" % (P0, P1))
        return False
        
    def normalOps(self):
        """ open the EV on each section with acceptable vacuum pressure
            this is useful after evacuating one of the vacuum sections
        """
        for vs in self.VSmap:
            if self.pressure(vs['name'])>self.acceptablePumpPressure:
                continue
            self.openValve(vs['name'], 'EV')        
         
    def evacuate(self, secName):
        """ check pump vacuum pressure, exit if section vacuum better than pump vacuum (pump off?)
            close the vent valve
            close the evacuation valve on all other vacuum sections
            close the gate valves (in case other sections are vented)
            if on a manifold:
                open the isolation valve after closing other isolation valves on the same manifold
            soft-open the evacuation valve
            wait until the vacuum pressure is sufficiently low (10 mbar??)
            open the evacuation valve
        """
        if self.pressure(secName)<self.pressure("pump"):
            print("vacuum pressure in this section is already better than the pump pressure.")
            return
        
        ns = self.VSindex[secName]
        self.closeValve(secName, "VV")
        self.closeValve(secName, "GV")   
        
        for vs in self.VSmap:
            if vs['name']==secName:
                continue
            self.closeValve(vs['name'], 'EV')
        
        self.openValve(secName, "EV", softOpen=True)
        t0 = time.time()
        while True:
            P0 = self.pressure(secName)
            t1 = time.time()
            print("pressure in %s: %.3f, time lapses: %d     \r"%(secName,P0,t1-t0), end="")
            sys.stdout.flush()
            time.sleep(1)
            if P0<10.:
                print("pressure in %s: %.3f, fully opening EV.     \n"%(secName,P0))
                break
        self.openValve(secName, "EV")
    
    def vent(self, secName):
        """ close gate valves on either end
            close the evacuation valve
            if on a manifold:
                open the isolation valve after closing other isolation valves on the same manifold
            soft-open the vent valve
            wait until the vacuum pressure is sufficiently high (10 mbar??)
            open the vent valve
        """
        self.closeValve(secName, "GV")
        self.closeValve(secName, "EV")
        t0 = time.time()
        self.openValve(secName, "VV", softOpen=True)
        while True:
            P0 = self.pressure(secName)
            t1 = time.time()
            print("pressure in %s: %.3f, time lapses: %d    \r"%(secName,P0,t1-t0), end="")
            sys.stdout.flush()
            time.sleep(1)
            if P0>500.:
                print("pressure in %s: %.3f, fully opening VV.   \n"%(secName,P0))
                break
        self.openValve(secName, "VV")
    
    def openValve(self, secName, valveType, softOpen=False, checkPumpPressure=False):
        """ valveType should be "EV", "VV", "IV", "GV" 
            EV/VV: check pump pressure if EV
                if the section is attached to a manifold, 
                    close all other IVs on the manifold, then open IV 
                    open the EV/VV on the manifold
            IV: if the manifold EV is open, check against pressure on other branches of the manifold
                if the manifold VV is open, just open it
            GV: both ends of the vacuum section, check pressure of the upstream and downstream sections
        """
        ns = self.VSindex[secName]
        P0 = self.pressure(secName)
        mf = self.findManifold(secName)
        if valveType=="GV":
            # allow GV open on one side only
            usGV, dsGV = self.VSmap[ns]["GVs"]
            # check pressure 
            if usGV!=None:
                P1 = self.pressure(self.VSmap[ns-1]["name"])
                if self.allowToOpen(P0, P1):
                    usGV.open()
            if dsGV!=None:
                P1 = self.pressure(self.VSmap[ns+1]["name"])
                if self.allowToOpen(P0, P1):
                    dsGV.open()
        elif valveType=="EV":
            P1 = self.pressure("pump")
            if checkPumpPressure and P1>self.acceptablePumpPressure:
                raise Exception("pump pressure is not adequate for evacuation.")
            if mf!=None:
                for vs in mf['vacSecs']:
                    if vs!=secName:
                        self.closeValve(vs, "IV")
                self.VSmap[ns]["IV"].open()
                EV = mf["EV"]
            else:
                EV = self.VSmap[ns]["EV"]
            EV.open(softOpen=softOpen)
        elif valveType=="VV":
            if mf!=None:
                for vs in mf['vacSecs']:
                    if vs!=secName:
                        self.closeValve(vs, "IV")
                self.VSmap[ns]["IV"].open()
                VV = mf["VV"]
            else:
                VV = self.VSmap[ns]["VV"]
            VV.open(softOpen=softOpen)
        elif valveType=="IV":
            if mf==None:
                raise Exception("vacuum section %s does not have IV" % secName)
            if mf['VV'].status>0.1:
                self.VSmap[ns]["IV"].open()
            elif mf['EV'].status>0.1:
                # open only if pressure difference between pump and vacSection is small
                # could also check the pressure on other branches of the manifold, but this is easier
                P1 = self.pressure("pump")
                if self.allowToOpen(P0, P1):
                    self.VSmap[ns]["IV"].open()
            else: # manifold vacuum pressure is unknown
                raise Exception("evacuate/vent using the EV/VV on the manifold instead.")
        else:
            raise Exception("Unknown valveType: ", valveType)
    
    def closeValve(self, secName, valveType):
        """ same types as above
        """
        ns = self.VSindex[secName]
        mf = self.findManifold(secName)
        if valveType=="GV":
            for gv in self.VSmap[ns]["GVs"]:
                if gv!=None:
                    gv.close()
        elif valveType=="EV":
            if mf is None:
                self.VSmap[ns]["EV"].close()
            else:
                #raise Exception("vacuum section %s does not have EV" % secName)
                mf['EV'].close()
        elif valveType=="VV":
            if mf is None:
                self.VSmap[ns]["VV"].close()
            else:
                #raise Exception("vacuum section %s does not have VV" % secName)
                mf['VV'].close()
        elif valveType=="IV":
            if mf!=None:
                self.VSmap[ns]["IV"].close()
            else:
                raise Exception("vacuum section %s does not have IV" % secName)
        else:
            raise Exception("Unknown valveType: ", valveType)

# Maxi gauge controller IOC running on xf16idc-ioc1
            
ESVacSys = VacuumSystem(MKSGauge("XF:16IDC-VA{ES-TCG:1}"))
ESVacSys.appendManifold("EMmf", 
                        ["XF:16IDC-VA{ES-EV:3}", "XF:16IDC-VA{ES-EV:SoftPump3}"], 
                        ["XF:16IDC-VA{ES-VV:3}", "XF:16IDC-VA{ES-VV:SoftPump3}"])

ESVacSys.appendSection("SS", MKSGauge("XF:16IDB-VA{Chm:SS-TCG:2}"), 
                       EVName=["XF:16IDB-VA{Chm:SS-EV:1}", "XF:16IDB-VA{Chm:SS-EV:SoftPump1}"], 
                       VVName=["XF:16IDB-VA{Chm:SS-VV:1}", "XF:16IDB-VA{Chm:SS-VV:SoftPump1}"],
                       downstreamGVName="XF:16IDC-VA{Chm:SS-GV:1}")

ESVacSys.appendSection("SF", MKSGauge("XF:16IDB-VA{Chm:SF-TCG:1}"), 
                       EVName=["XF:16IDC-VA{ES-EV:2}", "XF:16IDC-VA{ES-EV:SoftPump2}"], 
                       VVName=["XF:16IDC-VA{ES-VV:2}", "XF:16IDC-VA{ES-VV:SoftPump2}"],
                       downstreamGVName="XF:16IDC-VA{Chm:SF-GV:1}")

ESVacSys.appendSection("microscope", MaxiGauge("XF:16IDC-VA:{ES-Maxi:1}"), #MKSGauge("XF:16IDB-VA{EM-TCG:2}"), 
                       manifoldName="EMmf", IVName="XF:16IDC-VA{ES-EV:Micrscp}",
                       downstreamGVName=None)

ESVacSys.appendSection("nosecone", MaxiGauge("XF:16IDC-VA:{ES-Maxi:2}"), #MKSGauge("XF:16IDB-VA{EM-TCG:1}", 
                       manifoldName="EMmf", IVName="XF:16IDC-VA{ES-EV:Nosecone}",
                       downstreamGVName="XF:16IDC-VA{EM-GV:1}")

ESVacSys.appendSection("WAXS", MKSGauge("XF:16IDB-VA{det:WAXS-TCG:1}"), 
                       EVName=["XF:16IDC-VA{ES-EV:4}", "XF:16IDC-VA{ES-EV:SoftPump4}"], 
                       VVName=["XF:16IDC-VA{ES-VV:4}", "XF:16IDC-VA{ES-VV:SoftPump4}"],
                       downstreamGVName=None)