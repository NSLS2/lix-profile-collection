# coding: utf-8
#
#    Project: BioCAT user beamline control software (BioCON)
#             https://github.com/biocatiit/beamline-control-user
#
#
#    Principal author:       Jesse Hopkins
#
#    This is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This software is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this software.  If not, see <http://www.gnu.org/licenses/>.
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import object, range, map
from io import open
import six

import os
import glob
import time
import datetime
import logging
import sys
import threading
from collections import deque
import traceback
import copy

if __name__ != '__main__':
    logger = logging.getLogger(__name__)

import clr
import numpy as np

#NOTE: May need to change agilent directory or various verison numbers below.

agilent_dir = 'C:/Program Files (x86)/Agilent Technologies/'

# Add dlls from Agilent OpenLAB Services directory
services_dir = os.path.join(agilent_dir, 'OpenLAB Services')

clr.AddReference(os.path.join(services_dir, 'Common',
    'Agilent.OpenLab.SharedServices.dll'))
clr.AddReference(os.path.join(services_dir, 'Common',
    'Agilent.OpenLab.SharedServices.Common.dll'))
clr.AddReference(os.path.join(services_dir, 'Server',
    'Agilent.OpenLab.Storage.dll'))

# Add dlls from Microsoft.Net directory
net_dir = 'C:/Windows/Microsoft.Net/assembly/'

clr.AddReference(os.path.join(net_dir, 'GAC_32',
    'Agilent.OpenLAB.Acquisition.AutomationInstrument',
    'v4.0_2.7.0.0__968ccb09b2a5fe74',
    'Agilent.OpenLAB.Acquisition.AutomationInstrument.dll'))
clr.AddReference(os.path.join(net_dir,  'GAC_32',
    'Agilent.OpenLAB.Acquisition.AutomationCore',
    'v4.0_2.7.0.0__968ccb09b2a5fe74',
    'Agilent.OpenLAB.Acquisition.AutomationCore.dll'))
clr.AddReference(os.path.join(net_dir,  'GAC_MSIL',
    'Agilent.OpenLab.DataAnalysis.Api.Client',
    'v4.0_2.7.0.0__504c62913ba04614',
    'Agilent.OpenLab.DataAnalysis.Api.Client.dll'))
clr.AddReference(os.path.join(net_dir,  'GAC_MSIL',
    'Agilent.OpenLab.DataAnalysis.Api',
    'v4.0_2.7.0.0__646026e6e9aac423',
    'Agilent.OpenLab.DataAnalysis.Api.dll'))

# Add dlls from Agilent OpenLab Acquisition directory
acquisition_dir =  os.path.join(agilent_dir, 'OpenLAB Acquisition')

clr.AddReference(os.path.join(acquisition_dir,
    'Agilent.OpenLab.Framework.DataAccess.CoreTypes.dll'))
clr.AddReference(os.path.join(acquisition_dir,
    'Agilent.OpenLab.RawData.dll'))


from Agilent.OpenLab.SharedServices import Connection
from Agilent.OpenLAB.Acquisition.AutomationInstrument import InstrumentController
from Agilent.OpenLAB.Acquisition.AutomationCore import SingleRunParams
from Agilent.OpenLAB.Acquisition.AutomationCore import SequenceRecord, SequenceSet, SequenceSetType, SampleType
from Agilent.OpenLAB.Acquisition.AutomationCore import DeviceStatesEnum
from Agilent.OpenLAB.Acquisition.AutomationCore import ResourceIdAndValue
import System.Collections.ObjectModel
from System.Collections.Generic import Dictionary, List
from System import String, Int32, Guid, Array
observable_collection = getattr(System.Collections.ObjectModel, 'ObservableCollection`1')

def convert_volume(volume, u1, u2):
    if u1.lower() in ['nl', 'ul', 'ml'] and u2.lower() in ['nl', 'ul', 'ml']:
        if u1.lower() != u2.lower():
            if ((u1.lower() == 'nl' and u2.lower() == 'ul')
                or (u1.lower() == 'ul' and u2.lower() == 'ml')):
                volume = volume/1000.
            elif u1.lower() == 'nl' and u2.lower() == 'ml':
                volume = volume/1000000.
            elif ((u1.lower() == 'ml' and u2.lower() == 'ul')
                or (u1.lower() == 'ul' and u2.lower() == 'nl')):
                volume = volume*1000.
            elif u1.lower() == 'ml' and u2.lower() == 'nl':
                volume = volume*1000000.

    return volume

def convert_time(time, u1, u2):
    if u1.lower() in ['s', 'min'] and u2.lower() in ['s', 'min']:
        if u1.lower() != u2.lower():
            if u1.lower() == 'min':
                time = time/60
            else:
                time = time*60

    return time

def convert_flow_rate(fr, u1, u2):
    v_u1, t_u1 = u1.split('/')
    v_u2, t_u2 = u2.split('/')

    fr = convert_volume(fr, v_u1, v_u2)
    fr = convert_time(fr, t_u1, t_u2)

    return fr

def convert_flow_accel(accel, u1, u2):
    v_u1, t_u1 = u1.split('/')
    v_u2, t_u2 = u2.split('/')

    accel = convert_volume(accel, v_u1, v_u2)
    accel = convert_time(accel, t_u1, t_u2)
    accel = convert_time(accel, t_u1, t_u2)

    return accel

def convert_pressure(pressure, u1, u2):
    if (u1.lower() in ['psi', 'mpa', 'bar', 'mbar']
        and u2.lower() in ['psi', 'mpa', 'bar', 'mbar']):

        if u1.lower() != u2.lower():
            if u1.lower() == 'psi' and u2.lower() == 'mpa':
                pressure = pressure/145.038
            elif u1.lower() == 'psi' and u2.lower() == 'bar':
                pressure = pressure/14.5038
            elif u1.lower() == 'psi' and u2.lower() == 'mbar':
                pressure = 1000*pressure/14.5038
            elif u1.lower() == 'mpa' and u2.lower() == 'psi':
                pressure = pressure*145.038
            elif u1.lower() == 'mpa' and u2.lower() == 'bar':
                pressure = pressure*10
            elif u1.lower() == 'mpa' and u2.lower() == 'mbar':
                pressure = 1000*pressure*10
            elif u1.lower() == 'bar' and u2.lower() == 'psi':
                pressure = pressure*14.5038
            elif u1.lower() == 'bar' and u2.lower() == 'mpa':
                pressure = pressure/10
            elif u1.lower() == 'bar' and u2.lower() == 'mbar':
                pressure = pressure*1000
            elif u1.lower() == 'mbar' and u2.lower() == 'psi':
                pressure = pressure*14.5038/1000
            elif u1.lower() == 'mbar' and u2.lower() == 'mpa':
                pressure = pressure/10/1000
            elif u1.lower() == 'mbar' and u2.lower() == 'bar':
                pressure = pressure/1000

    return pressure

class HPLC(object):
    """
    Basic control class for an HPLC
    """

    def __init__(self, name, device, comm_lock=None):
        """
        """

        self._device = device
        self.name = name

        self._flow_base_units = 'mL/min'
        self._flow_units = self._flow_base_units
        self._pressure_base_units = 'bar'
        self._pressure_units = 'bar'

        self._target_flow_rate = 0

        if comm_lock is None:
            self.comm_lock = threading.Lock()
        else:
            self.comm_lock = comm_lock

        self._connected = False

        self._connect()


    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__, self.name,
            self._device)

    def __str__(self):
        return '{} {}, connected to {}'.format(self.__class__.__name__,
            self.name, self._device)

    def _connect(self):
        if not self._connected:
            self._connected = True

    @property
    def flow_units(self):
        """
        Sets and returns the pump flow rate units. This can be set to:
        nL/s, nL/min, uL/s, uL/min, mL/s, mL/min. Changing units keeps the
        flow rate constant, i.e. if the flow rate was set to 100 uL/min, and
        the units are changed to mL/min, the flow rate is set to 0.1 mL/min.

        :type: str
        """
        return self._flow_units

    @flow_units.setter
    def flow_units(self, units):
        old_units = self._flow_units

        if units in ['nL/s', 'nL/min', 'uL/s', 'uL/min', 'mL/s', 'mL/min']:
            self._flow_units = units

            logger.info("Changed pump %s units from %s to %s", self.name,
                old_units, units)
        else:
            logger.warning(("Failed to change HPLC %s units, units supplied "
                "were invalid: %s"), self.name, units)

    @property
    def pressure_units(self):
        """
        Sets and returns the pump flow rate units. This can be set to:
        nL/s, nL/min, uL/s, uL/min, mL/s, mL/min. Changing units keeps the
        flow rate constant, i.e. if the flow rate was set to 100 uL/min, and
        the units are changed to mL/min, the flow rate is set to 0.1 mL/min.

        :type: str
        """
        return self._pressure_units

    @pressure_units.setter
    def pressure_units(self, units):
        old_units = self._pressure_units

        if units.lower() in ['psi', 'bar', 'mpa', 'mbar']:
            self._pressure_units = units

            logger.info("Changed pump %s pressure units from %s to %s", self.name, old_units, units)
        else:
            logger.warning("Failed to change pump %s pressure units, units supplied were invalid: %s", self.name, units)

    def _convert_volume(self, volume, u1, u2):
        volume = convert_volume(volume, u1, u2)
        return volume

    def _convert_time(self, time, u1, u2):
        time = convert_time(time, u1, u2)
        return time

    def _convert_flow_rate(self, fr, u1, u2):
        fr = convert_flow_rate(fr, u1, u2)
        return fr

    def _convert_flow_accel(self, accel, u1, u2):
        accel = convert_flow_accel(accel, u1, u2)
        return accel

    def _convert_pressure(self, pressure, u1, u2):
        pressure = convert_pressure(pressure, u1, u2)
        return pressure

    def get_pressure(self):
        return None

    def get_flow_rate(self):
        return None

    def stop(self):
        """Stops all pump flow."""
        pass #Should be implimented in each subclass

    def disconnect(self):
        """Close any communication connections"""
        self._connected = False

class AgilentHPLC(HPLC):
    """
    Agilent specific HPLC control
    """

    def __init__(self, name, device, instrument_name='', project_name='',
        get_inst_method_on_start=True, comm_lock=None):
        """
        Initializes an Agilent HPLC using the OpenLab CDS SDK

        Parameters
        ----------
        name: str
            Device name for python
        device: str
            Connection string, e.g. "net.pipe://localhost/Agilent/OpenLAB/"
        instrument_name: str
            Instrument name as shown in the Agilent Control Panel, e.g. "HPLC-1"
        project_name: str
            Project as shown in the Agilent Control Panel, e.g. "Demo"

        """

        self._instrument_name = instrument_name
        self._project_name = project_name
        self._get_inst_method_on_start = get_inst_method_on_start

        self._current_method = None
        self._current_sample_prep_method = None

        # Seems to be something weird with the .NET callbacks,
        # so move them back to python in a thread
        self._callback_stop = threading.Event()
        self._callback_queue = deque()
        self._callback_cmds = {
            'on_controller_connect' : self._on_controller_connected,
            'on_generic'            : self._on_generic,
            'on_as_drawer_config'   : self._on_as_drawer_config,
            'on_run_queue_status'   : self._on_run_queue_status,
            'on_run_record_changed' : self._on_run_record_changed,
            'on_run_collection'     : self._on_run_collection,
            'on_trace_added'        : self._on_trace_added,
            'on_trace_data'         : self._on_trace_data,
            'on_trace_removed'      : self._on_trace_removed,
            'on_x_trace_change'     : self._on_x_trace_change,
            'on_run_start'          : self._on_run_start,
            'on_inst_state_changed' : self._on_inst_state_changed,
            'on_disconnect'         : self._on_disconnect,
            }

        self._callback_thread = threading.Thread(target=self._run_from_callback)
        self._callback_thread.daemon = True
        self._callback_thread.start()

        self._has_pump = False
        self._has_autosampler = False
        self._has_uv = False
        self._pumps = []
        self._autosamplers = []
        self._uvs = []

        self._traces = {}
        self._trace_data = {}
        self._trace_lookup = {}
        self._run_starts = []
        self._trace_history_length = 120.0 #time in minutes
        self._trace_lock = threading.Lock()

        self._pump_data = {}
        self._autosampler_data = {}
        self._uv_data = {}

        self._inst_errors = {}
        self._errors_lock = threading.Lock()

        self._run_ids = {}
        self._run_data = {}
        self._run_queue = deque()
        self._run_lock = threading.Lock()
        self._run_queue_status = 'Default'

        self._reconnect_tries = 0

        HPLC.__init__(self, name, device, comm_lock=comm_lock)

        self.pump_prop_ids = ['Pressure', 'Pressure_DisplayValue', 'Flow',
            'Flow_DisplayValue', 'PumpPower', 'BottleFilling_CurrentAbsolute',
            'BottleFilling2_CurrentAbsolute', 'BottleFilling3_CurrentAbsolute',
            'BottleFilling4_CurrentAbsolute', 'BottleFilling_MaximumAbsolute',
            'BottleFilling2_MaximumAbsolute', 'BottleFilling3_MaximumAbsolute',
            'BottleFilling4_MaximumAbsolute',
            ]

        self.sampler_prop_ids = ['Thermostat_PowerOn', 'Thermostat_Temperature']

        self.uv_prop_ids = ['UVLampState', 'IsVisLampOn', 'Signal_Current',
            'Signal2_Current', 'Signal3_Current', 'Signal4_Current',
            'Signal5_Current', 'Signal6_Current', 'Signal7_Current',
            'Signal8_Current',
            ]

    def _connect(self):
        logger.info('Agilent HPLC %s connecting: %s at %s with project %s',
            self.name, self._instrument_name, self._device, self._project_name)
        self._connection = Connection(self._device)
        self._user_ticket = self._connection.GetTicketContainer().ToString()

        # #Get available instruments
        instruments = self._connection.Instruments.GetAllInstrumentsInfo()

        self._instrument_data = {}
        for instrument in instruments:
            inst = self._connection.Instruments.GetInstrument(instrument.Id)
            self._instrument_data[inst.Name] = {'id': instrument.Id}

            if inst.Name == self._instrument_name:
                self._instrument = inst

        # #Get available projects
        projects = self._connection.Projects.GetAllProjectsInfo()

        self._project_data = {}
        for project in projects:
            self._project_data[project.Name] = {'id': project.Id}

        self._project_path = self._connection.Projects.GetProject(
            self._project_data[self._project_name]['id']).RootPath.AbsolutePath

        # Connect to the controller
        self.controller = InstrumentController()
        self.controller.AppInitialized += self._on_connected_callback
        self.controller.ModuleConfigurationChanged += self._on_generic_callback
        self.controller.SampleContainerConfigChanged += self._on_as_drawer_callback
        self.controller.RunQueueStatusChanged += self._on_run_queue_status_callback
        self.controller.RunRecordChanged += self._on_run_record_changed_callback
        self.controller.RunRecordCollectionChanged += self._on_run_collection_callback
        self.controller.InstrumentTraceAddedEvent += self._on_trace_added_callback
        self.controller.InstrumentPointsChangeEvent += self._on_trace_data_callback
        self.controller.InstrumentTraceRemovedEvent += self._on_trace_removed_callback
        self.controller.InformClientCorrectXAxisEvent += self._on_x_trace_change_callback
        self.controller.InformClientRunStartedEvent += self._on_run_start_callback
        self.controller.InstrumentStateInfoChangedEvent += self._on_inst_state_changed_callback
        self.controller.DisconnectEvent += self._on_disconnect_callback

        self.controller.EstablishConnection(self._device, self._user_ticket,
            '{}'.format(self._instrument_data[self._instrument_name]['id']),
            '{}'.format(self._project_data[self._project_name]['id']))

    def _on_generic_callback(self, source, args):
        self._callback_queue.append(['on_generic', source ,args])

    def _on_generic(self, source, args):
        print(source)
        print(args)

        self.generic_data = [source, args]

    def _on_as_drawer_callback(self, source, args):
        self._callback_queue.append(['on_as_drawer_config', source ,args])

    def _on_as_drawer_config(self, source, args):
        # print(source)
        # print(args)
        # print(args.Key)
        # print(args.Containers)
        # print(args.ContainerConfig)

        # with open('container_xml.xml', 'w') as f:
        #     f.writelines(args.ContainerConfig)
        pass

    def _on_run_queue_status_callback(self, source, args):
        self._callback_queue.append(['on_run_queue_status', source ,args])

    def _on_run_queue_status(self, source, args):
        self._run_queue_status = args.RunQueueStatus.ToString()

    def _on_run_record_changed_callback(self, source, args):
        self._callback_queue.append(['on_run_record_changed', source ,args])

    def _on_run_record_changed(self, source, args):
        rec = args.UpdatedRecord
        run_id = rec.Id.ToString()
        status = rec.Status.ToString()

        self.updated_record = rec

        with self._run_lock:
            try:
                current_inj = rec['CurrentInjection']
                total_inj = rec['TotalInjections']
            except Exception:
                current_inj = None
                total_inj = None

            try:
                acq_method = rec['AcquisitionMethod']
            except Exception:
                acq_method = None

            if run_id in self._run_ids:
                name = self._run_ids[run_id]
                self._run_data[name]['status'] = status
                if current_inj is not None:
                    self._run_data[name]['current_injection'] = current_inj
                if total_inj is not None:
                    self._run_data[name]['total_injections'] = total_inj

                if acq_method is not None:
                    methods = self._run_data[name]['acq_method']
                    if (methods is not None and acq_method not in methods
                        and os.path.splitext(acq_method)[0] not in methods):
                        methods = methods.append(acq_method)
                        self._run_data[name]['acq_method'] = methods
                    elif methods is None:
                        self._run_data[name]['acq_method'] = [acq_method,]

            else:
                if acq_method is None:
                    acq_method = []
                name = run_id
                self._run_ids[run_id] = name
                self._run_data[name] ={
                    'status'            : status,
                    'run_id'            : run_id,
                    'guid'              : rec.Id,
                    'params'            : [],
                    'rtype'             : '',
                    'total_injections'  : total_inj,
                    'current_injection' : current_inj,
                    'acq_method'        : acq_method,
                }

                self._run_queue.append(name)

            lstatus = status.lower()
            if (lstatus == 'aborted' or lstatus == 'completed'
                or lstatus == 'Unexisting'):
                try:
                    self._run_queue.remove(name)
                except ValueError:
                    pass

    def _on_run_collection_callback(self, source, args):
        self._callback_queue.append(['on_run_collection', source ,args])

    def _on_run_collection(self, source, args):
        run_records = args.RunRecords

        for rec in run_records:
            run_id = rec.Id.ToString()
            status = rec.Status.ToString()
            lstatus = status.lower()
            rtype = rec.SampleRunType.ToString()

            with self._run_lock:
                if run_id in self._run_ids:
                    name = self._run_ids[run_id]
                    self._run_data[name]['status'] = status

                else:
                    name = run_id

                    if rtype.lower() == 'singlerun':
                        nruns = 1
                    else:
                        nruns = None
                    self._run_ids[run_id] = name
                    self._run_data[name] ={
                        'status'            : status,
                        'run_id'            : run_id,
                        'guid'              : rec.Id,
                        'params'            : [],
                        'rtype'             : rtype,
                        'total_injections'  : nruns,
                        'current_injection' : None,
                        'acq_method'        : [],
                    }

                    if (lstatus != 'aborted' or lstatus != 'completed'
                        or lstatus != 'Unexisting'):
                        self._run_queue.append(name)

                if (lstatus == 'aborted' or lstatus == 'completed'
                    or lstatus == 'Unexisting'):
                    try:
                        self._run_queue.remove(name)
                    except ValueError:
                        pass

    def _on_trace_added_callback(self, source, args):
        self._callback_queue.append(['on_trace_added', source ,args])

    def _on_trace_added(self, source, args):
        trace = args.Trace
        with self._trace_lock:
            if trace.SignalID in self._trace_lookup.values():
                old_name = self._traces[trace.SignalID].Title
                del self._trace_lookup[old_name]

            self._traces[trace.SignalID] = trace
            self._trace_lookup[trace.Title] = trace.SignalID

        self.controller.SubscribePlotData(trace)

    def _on_trace_data_callback(self, source, args):
        self._callback_queue.append(['on_trace_data', source ,args])

    def _on_trace_data(self, source, args):
        signal_id = args.SignalID
        xvals = args.XValues
        yvals = args.YValues

        with self._trace_lock:
            if signal_id in self._trace_data:
                signal_data = self._trace_data[signal_id]
                signal_data[0].extend(xvals)
                signal_data[1].extend(yvals)
            else:
                self._trace_data[signal_id] = [list(xvals), list(yvals)]

            self._prune_history(signal_id)

    def _prune_history(self, signal_id):
        signal_data = self._trace_data[signal_id]
        time = signal_data[0]
        signal = signal_data[1]

        cur_time = time[-1]

        if cur_time - time[0] > self._trace_history_length:
            index = 1

            while cur_time - time[index] > self._trace_history_length:
                index += 1

            time = time[index:]
            signal = signal[index:]

            self._trace_data[signal_id] = [time, signal]

    def _on_trace_removed_callback(self, source, args):
        self._callback_queue.append(['on_trace_removed', source ,args])

    def _on_trace_removed(self, source, args):
        trace = args.Trace

        self.controller.UnubscribePlotData(trace)

        with self._trace_lock:
            del self._traces[trace.SignalID]
            del self._trace_lookup[trace.Title]
            del self._trace_data[trace.SignalID]

    def _on_x_trace_change_callback(self, source, args):
        self._callback_queue.append(['on_x_trace_change', source ,args])

    def _on_x_trace_change(self, source, args):
        x_offset = args.XAdjustValue

        with self._trace_lock:
            for data in self._trace_data.values():
                data[0] = list(np.array(data[0])-x_offset)

            for i in range(len(self._run_starts)):
                self._run_starts[i] -= x_offset


    def _on_run_start_callback(self, source, args):
        self._callback_queue.append(['on_run_start', source ,args])

    def _on_run_start(self, source, args):
        start_time = args.MarkerPosition

        with self._trace_lock:
            self._run_starts.append(start_time)

    def _on_inst_state_changed_callback(self, source, args):
        self._callback_queue.append(['on_inst_state_changed', source ,args])

    def _on_inst_state_changed(self, source, args):
        state_info = args.StateInfo

        with self._errors_lock:
            self._inst_errors = {}
            for key in state_info.Keys:
                self._inst_errors[key] = list(state_info[key])

    def _on_disconnect_callback(self, source, args):
        self._callback_queue.append(['on_disconnect', source, args])

    def _on_disconnect(self, source, args):
        self.connected = False
        self._reconnect_tries += 1
        logger.error('Agilent HPLC %s unexpected disconnected.', self.name)

        if self._reconnect_tries < 2:
            try:
                self.reconnect()
            except Exception:
                pass

    def _on_connected_callback(self, source, args):
        self._callback_queue.append(['on_controller_connect', source, args])

    def _on_controller_connected(self, source, args):
        self.controller.AppInitialized -= self._on_connected_callback

        while not self.controller.IsConnected:
            time.sleep(0.1)

        self._reconnect_tries = 0

        self._modules = self.controller.Modules

        for module in self._modules:
            if module.DeviceType.lower() == 'pump':
                self._has_pump = True
                self._pumps.append(module.Hashkey)
                self._pump_data[module.Hashkey] = {}
            elif module.DeviceType.lower() == 'sampler':
                self._has_autosampler = True
                self._autosamplers.append(module.Hashkey)
                self._autosampler_data[module.Hashkey] = {}
            elif module.DeviceType.lower() == 'detector':
                self._has_uv = True
                self._uvs.append(module.Hashkey)
                self._uv_data[module.Hashkey] = {}

        # This uploadcurrentmethod sometime just randomly hangs
        # a sleep helps a bit
        time.sleep(1)
        if self._get_inst_method_on_start:
            self.get_current_method_from_instrument()

        self._get_pump_properties()
        self._get_autosampler_properties()
        self._get_uv_properties()
        self._get_injection_properties()

        self.controller.ConnectInstrumentTraces()

        self._connected = self.controller.IsConnected

        logger.info(('Agilent HPLC %s connected: %s at %s with project %s. '
            'Success: %s'), self.name, self._instrument_name, self._device,
            self._project_name, self._connected)

    def get_methods(self):
        """
        Gets available acquisition methods.

        Returns
        -------
        methods: list
            A list of the path to available acquisition methods relative to
            the base methods directory
        """
        methods = []

        base_path =  os.path.join(self._project_path, 'Methods')

        for dirpath, dirnames, fnames in os.walk(base_path):

            for fname in fnames:
                ext = os.path.splitext(fname)[1]

                if ext == '.amx':
                    rel_base_path = os.path.relpath(base_path, dirpath)

                    method_name = os.path.join(rel_base_path, fname)

                    methods.append(method_name)

        return methods

    def get_sample_prep_methods(self):
        """
        Gets available acquisition methods.

        Returns
        -------
        methods: list
            A list of the path to available acquisition methods relative to
            the base methods directory
        """
        methods = []

        base_path =  os.path.join(self._project_path, 'Methods')

        for dirpath, dirnames, fnames in os.walk(base_path):

            for fname in fnames:
                ext = os.path.splitext(fname)[1]

                if ext == '.smx':
                    rel_base_path = os.path.relpath(base_path, dirpath)

                    method_name = os.path.join(rel_base_path, fname)

                    methods.append(method_name)

        return methods

    def _get_pump_properties(self, pump_id=None):
        if pump_id is None:
            pump_list = self._pumps
        else:
            pump_list = [pump_id,]

        for pump in pump_list:
            res = self.controller.GetModuleStatusPropertiesAsync(pump,
                self.pump_prop_ids).Result

            for item in res.ResultData:
                self._pump_data[pump][item.PropertyId] = item.PropertyValue

    def _get_autosampler_properties(self, autosampler_id=None):
        if autosampler_id is None:
            autosampler_list = self._autosamplers
        else:
            autosampler_list = [autosampler_id,]

        for autosampler in autosampler_list:
            res = self.controller.GetModuleStatusPropertiesAsync(autosampler,
                self.sampler_prop_ids).Result

            for item in res.ResultData:
                self._autosampler_data[autosampler][item.PropertyId] = item.PropertyValue

    def _get_uv_properties(self, uv_id=None):
        if uv_id is None:
            uv_list = self._uvs
        else:
            uv_list = [uv_id,]

        for uv in uv_list:
            res = self.controller.GetModuleStatusPropertiesAsync(uv,
                self.uv_prop_ids).Result

            for item in res.ResultData:
                self._uv_data[uv][item.PropertyId] = item.PropertyValue

    def _get_injection_properties(self):
        # Get injection sources
        inj_sources = self.controller.InjectionSources

        self.injection_devices = {}
        for inj_source in inj_sources:
            self.injection_devices[inj_source.DisplayName] = inj_source

            if inj_source.DisplayName == 'HipAls':
                self.inj_source = 'HipAls'

    def get_instrument_status(self):
        """
        Returns the instrument status.

        Returns
        -------
        status: str
            The instrument status. Possible states are: Offline, Unknown,
            Error, Run, Injecting, PostRun, PreRun, NotReady, Standby,
            Idle, Tune
        """
        state = self.controller.CurrentInstrumentState.ToString()

        return state

    def get_run_queue_status(self):
        """
        Gets the run queue status. Can be:

        *   Default - No item is Paused, Editing, or In Review, queue is not
            being reordered.
        *   Paused - Queue is paused
        *   Editing - At least one item in the queue has the status
            'Editing'
        *   InReview - At least one item in the queue has the status
            'In Review'
        *   ReorderPendingRuns - The queue is being reordered
        """
        return self._run_queue_status

    def get_run_status(self, name):
        """
        Gets the status of a run. Can be:

        *   Pending - Run is waiting for previous runs to complete
        *   Acquiring - During data acquisition
        *   Aborting - Run is being aborted
        *   Aborted - Run is aborted
        *   Completed - Run is complete
        *   Validating - Being validated by server
        *   Submitted - On submission to run queue
        *   Editing - During editing on the running item
        *   Processing - During processing
        *   Paused - Run is paused
        *   Scanning - During scanning
        *   InReview - During review of the running item
        *   Suspended - During execution of priority run
        *   Reporting - During reporting
        *   Unexisting
        *   Waiting

        Parameters
        ----------
        name: str
            The name provided when the run was submitted.

        Returns
        -------
        status: str
            The run status as detailed above.
        """
        with self._run_lock:
            if name in self._run_data:
                status = self._run_data[name]['status']
            else:
                status = ''
                logger.error('Requested run %s status from HPLC %s but '
                    'run does not exist.', name, self.name)

        return status

    def get_run_queue(self):
        """
        Returns the name and status of all items in the run queue.

        Returns
        -------
        run_queue: list
            A list where each item is a tuple consisting of: the item name,
            the item status, the current injection value of the item
            (e.g. 1 is first injection, 2 is second injection, None means no data/
            no injection yet), and the total injections (e.g. for a sequence with
            two items in it, there are 2 total injections).
        """
        run_queue = []

        with self._run_lock:
            for name in self._run_queue:
                status = self._run_data[name]['status']
                cur_inj = self._run_data[name]['current_injection']
                total_inj = self._run_data[name]['total_injections']
                run_queue.append((name, status, cur_inj, total_inj))

        return run_queue

    def get_run_data(self, name):
        """
        Returns all the run data associated with the specified run.

        Returns
        -------
        run_data: dict
            A dictionary with the stored run data.
        """
        with self._run_lock:
            run_data = copy.copy(self._run_data[name])

        return run_data

    def get_available_data_traces(self):
        """
        Returns the names of all available data traces (e.g. flow rate, pressure,
        UV absorption).

        Returns
        -------
        trace_names: list
            A list of the names of each available data trace.
        """
        with self._trace_lock:
            trace_names = list(self._trace_lookup.keys())

        return trace_names

    def get_data_trace(self, trace_name):
        """
        Returns the time and signal data of the specified data trace.

        Parameters
        ----------
        trace_name: str
            The trace name. Should be one of the items returned by the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_available_data_traces` method.

        Returns
        -------
        data: list
            A list where the first entry is a list of time values (in minutes)
            and the second is a list of signal values. Returns an empty list
            if an invalid trace name is supplied.
        """


        with self._trace_lock:
            if trace_name in self._trace_lookup:
                trace_id = self._trace_lookup[trace_name]
                data = copy.copy(self._trace_data[trace_id])

            else:
                data = []
                logger.error(('HPLC %s has no data trace named %s, so no '
                    'data was returned'), self.name, trace_name)

        return data

    def get_data_trace_max_length(self):
        """
        Returns the maximum length of a data trace. For example, if
        the value is 120 (the default), 120 minutes worth of data are kept,
        and as new data is acquired older data will be dropped.

        Returns
        -------
        trace_length: float
            The maximum length of a data trace preserved in software in
            minutes.
        """
        with self._trace_lock:
            trace_length = copy.copy(self._trace_history_length)

        return trace_length



    def get_run_start_times(self):
        """
        Returns the run start times (most likely injection markers, unless
        you're doing something really odd).

        Returns
        -------
        start_times: list
            A list of run start times. Times are in minutes, and correspond
            to times that you'd get from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_data_trace` method.
        """

        with self._trace_lock:
            start_times = copy.copy(self._run_starts)

        return start_times

    def get_instrument_errors(self):
        """
        Returns any current instrument errors.

        Returns
        -------
        errors: dict
            A dictionary where the key is a module id and the value is
            a list of strings, where the strings are error messages.
        """

        with self._errors_lock:
            errors = copy.copy(self._inst_errors)

        return errors

    def get_current_method_from_instrument(self):
        """
        Gets the current method from the instrument and sets it as the
        loaded acquisition method.
        """
        result = self.controller.UploadCurrentMethodAsync().Result
        self._current_method = 'instrument'

    def _normalize_method_path(self, method_name, mtype):
        if mtype == 'acq':
            ext = '.amx'
        elif mtype == 'sample':
            ext = '.smx'
        elif mtype == 'proc':
            ext = '.pmx'

        method_name = '{}{}'.format(os.path.splitext(method_name)[0], ext)

        base_path =  os.path.join(self._project_path, 'Methods')
        method_path = os.path.join(base_path, method_name)
        method_path = os.path.abspath(os.path.expanduser(method_path))

        rel_base_path = os.path.relpath(base_path, os.path.split(method_path)[0])

        return method_path, rel_base_path

    def load_method(self, method_name):
        """
        Loads the specified method as the current acquisition method. Note
        that  this does not send the method settings to the instrument, to
        do that you would also need to call
        :py:meth:`AgilentHPLC.send_current_method_to_instrument`

        Parameters
        ----------
        method_name: str
            The method name relative to the top level OpenLab CDS Methods folder.
        """
        method_path, rel_base_path = self._normalize_method_path(method_name,
            'acq')

        if os.path.exists(method_path):
            self._current_method = os.path.join(rel_base_path,
                os.path.split(method_path)[1])

            self.controller.LoadAcquisitionMethod(method_path, True)

    def load_sample_prep_method(self, method_name):
        """
        Loads the specified method as the current sample prep method.

        Parameters
        ----------
        method_name: str
            The method name relative to the top level OpenLab CDS Methods folder.
        """
        method_path, rel_base_path = self._normalize_method_path(method_name,
            'sample')

        if os.path.exists(method_path):
            self._current_sample_prep_method = os.path.join(rel_base_path,
                os.path.split(method_path)[1])

            self.controller.LoadSamplePrepMethod(method_path, True)

    def get_pump_ids(self):
        """
        Returns the pump ids (Agilent hashkeys) that are used as the pump_id
        variable in various methods.

        Returns
        -------
        pump_ids: list
            A list of pump ids (strings).
        """

        return copy.copy(self._pumps)

    def get_autosampler_ids(self):
        """
        Returns the autosampler ids (Agilent hashkeys) that are used as the
        as_id variable in various methods.

        Returns
        -------
        autosampler_ids: list
            A list of autosampler ids (strings).
        """

        return copy.copy(self._autosamplers)

    def get_uv_ids(self):
        """
        Returns the uv detector ids (Agilent hashkeys) that are used as the
        uv_id variable in various methods.

        Returns
        -------
        uv_ids: list
            A list of uv ids (strings).
        """

        return copy.copy(self._uvs)

    def get_all_sample_prep_method_ids(self, as_id=None):
        """
        Gets the sample prep method ids, which can be used to set method
        properties for the specified autosampler. If no autosampler is
        selected, the first autosampler in the autosamplers list is used.

        Parameters
        ----------
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        method_ids: list
            A list of method ids (strings). Returns an empty list if
            no method ids are found (e.g. due to an invalid id).
        """

        as_id, success = self._validate_as_id(as_id)

        if not success:
            logger.error(('Failed to get HPLC %s autosampler method ids due '
                'to an invalid autosampler id'), self.name)

            method_ids = []

        else:
            _, res_descrips = self.controller.GetSamplePrepMethodResourceDescriptions(as_id)

            method_ids = [item.Id for item in res_descrips]

        return method_ids

    def get_sample_prep_method_values(self, method_ids, as_id=None):
        """
        Gets the values of sample prep method settings. If no autosampler
        is specified, the first autosampler in the autosamplers list is used.

        Parameters
        ----------
        method_ids: list
            A list of strings, where each string is a method id that can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_sample_prep_method_ids` method.

        Returns
        -------
        method_values: dict
            A dictionary of method values where the key is the method id
            and the value is the value of that setting in the currently loaded
            method. Returns an empty dictionary if no values are found.
        """

        # Need to figure out why this works in the test script but not
        # here
        as_id, success = self._validate_as_id(as_id)

        method_values = {}
        if not success:
            logger.error(('Failed to get HPLC %s sample prep method values '
                'due to an invalid autosampler id'), self.name)
        else:
            _, vals = self.controller.GetSamplePrepMethodResourceProperties(as_id,
                method_ids)

            for item in vals:
                method_values[item.PropertyId] = item.PropertyValue

        return method_values

    def _get_all_module_method_ids(self, module_id):
        _, res_descrips = self.controller.GetMethodResourceDescriptions(module_id)

        method_ids = [item.Id for item in res_descrips]

        return method_ids

    def get_all_pump_method_ids(self, pump_id=None):
        """
        Gets the pump method ids, which can be used to set method properties
        for the specified pump. If no pump is specified, the first pump in
        the pumps list is used.

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        method_ids: list
            A list of method ids (strings). Returns an empty list if
            no method ids are found (e.g. due to an invalid id).

        """
        pump_id, success = self._validate_pump_id(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump method ids due to an '
                'invalid pump id'), self.name)

            method_ids = []

        else:
            method_ids = self._get_all_module_method_ids(pump_id)

        return method_ids

    def get_all_autosampler_method_ids(self, as_id=None):
        """
        Gets the autosampler method ids, which can be used to set method
        properties for the specified autosampler. If no autosampler is
        specified, the first autosampler in the pumps list is used.

        Parameters
        ----------
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        method_ids: list
            A list of method ids (strings). Returns an empty list if
            no method ids are found (e.g. due to an invalid id).
        """
        as_id, success = self._validate_as_id(as_id)

        if not success:
            logger.error(('Failed to get HPLC %s autosampler method ids due '
                'to an invalid autosampler id'), self.name)

            method_ids = []

        else:
            method_ids = self._get_all_module_method_ids(as_id)

        return method_ids

    def get_all_uv_method_ids(self, uv_id=None):
        """
        Gets the detector method ids, which can be used to set method
        properties for the specified detector. If no detector is
        specified, the first detector in the pumps list is used.

        Parameters
        ----------
        uv_id: str
            The OpenLab CDS Hashkey for the detector module.

        Returns
        -------
        method_ids: list
            A list of method ids (strings). Returns an empty list if
            no method ids are found (e.g. due to an invalid id).

        """
        uv_id, success = self._validate_uv_id(uv_id)

        if not success:
            logger.error(('Failed to get HPLC %s uv method ids due to an '
                'invalid uv id'), self.name)

            method_ids = []

        else:
            method_ids = self._get_all_module_method_ids(uv_id)

        return method_ids

    def get_pump_method_values(self, method_ids, pump_id=None):
        """
        Gets the values of pump method settings. If no pump is specified,
        the first pump in the pumps list is used.

        Parameters
        ----------
        method_ids: list
            A list of strings, where each string is a method id that can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_pump_method_ids` method.

        Returns
        -------
        method_values: dict
            A dictionary of method values where the key is the method id
            and the value is the value of that setting in the currently loaded
            method. Returns an empty dictionary if no values are found.
        """

        # Need to figure out why this works in the test script but not
        # here
        pump_id, success = self._validate_pump_id(pump_id)

        method_values = {}
        if not success:
            logger.error(('Failed to get HPLC %s pump method values due to an '
                'invalid pump id'), self.name)
        else:
            _, vals = self.controller.GetMethodResourceProperties(pump_id,
                method_ids)

            for item in vals:
                method_values[item.PropertyId] = item.PropertyValue

        return method_values

    def get_autosampler_method_values(self, method_ids, as_id=None):
        """
        Gets the values of autosampler method settings. If no autosampler
        is specified, the first autosampler in the autosamplers list is used.

        Parameters
        ----------
        method_ids: list
            A list of strings, where each string is a method id that can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_pump_method_ids` method.

        Returns
        -------
        method_values: dict
            A dictionary of method values where the key is the method id
            and the value is the value of that setting in the currently loaded
            method. Returns an empty dictionary if no values are found.
        """

        # Need to figure out why this works in the test script but not
        # here
        as_id, success = self._validate_as_id(as_id)

        method_values = {}
        if not success:
            logger.error(('Failed to get HPLC %s autosampler method values '
                'due to an invalid autosampler id'), self.name)
        else:
            _, vals = self.controller.GetMethodResourceProperties(as_id,
                method_ids)

            for item in vals:
                method_values[item.PropertyId] = item.PropertyValue

        return method_values

    def get_uv_method_values(self, method_ids, uv_id=None):
        """
        Gets the values of uv detector method settings. If no detector is
        specified, the first detector in the uvs list is used.

        Parameters
        ----------
        method_ids: list
            A list of strings, where each string is a method id that can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_pump_method_ids` method.

        Returns
        -------
        method_values: dict
            A dictionary of method values where the key is the method id
            and the value is the value of that setting in the currently loaded
            method. Returns an empty dictionary if no values are found.
        """

        # Need to figure out why this works in the test script but not
        # here
        uv_id, success = self._validate_uv_id(uv_id)

        method_values = {}
        if not success:
            logger.error(('Failed to get HPLC %s autosampler method values '
                'due to an invalid autosampler id'), self.name)
        else:
            _, vals = self.controller.GetMethodResourceProperties(uv_id,
                method_ids)

            for item in vals:
                method_values[item.PropertyId] = item.PropertyValue

        return method_values

    def get_pressure(self, pump_id=None):
        """
        Returns the pump pressure for the specified pump. If no pump is
        specified, the first pump in the pumps list is used.

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        pressure: float
            The pressure in the HPLC's specified pressure_units. -1 is
            returned if pressure cannot be acquired.
        """
        pump_id, success = self._inner_get_pump_property(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump pressure due to '
                'invalid pump id'), self.name)

        if not success:
            return -1

        try:
            pressure = float(self._pump_data[pump_id]['Pressure'])
        except Exception:
            pressure = -1

        if pressure != -1:
            pressure = self._convert_pressure(pressure, self._pressure_base_units,
                self._pressure_units)

        return pressure

    def get_flow_rate(self, pump_id=None):
        """
        Returns the pump flow rate for the specified pump. If no pump is
        specified, the first pump in the pumps list is used. Note that this
        is very slow (~1-2 s) and seems to cache (so sometimes will seem fast).
        Probably better to go through the data traces.

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        flow_rate: float
            The flow rate in the HPLC's specified flow_units. -1 is
            returned if flow rate cannot be acquired.
        """
        pump_id, success = self._inner_get_pump_property(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump flow rate due to '
                'invalid pump id'), self.name)

        if not success:
            return -1

        try:
            flow_rate = float(self._pump_data[pump_id]['Flow'])
        except Exception:
            flow_rate = -1

        if flow_rate != -1:
            flow_rate = self._convert_flow_rate(flow_rate, self._flow_base_units,
                self._flow_units)

        return flow_rate

    def get_target_flow_rate(self, pump_id=None, update_method=True):
        """
        This returns the target flow rate of the currently running method
        for the specified pump. If no pump is specified, the first pump
        in the pumps list is used. Note that this will replace the loaded
        method with the method on the instrument.

        Returns
        -------
        flow_rate: float
            The target flow rate in the HPLC's specified flow_units. -1 is
            returned if flow rate cannot be acquired.
        update_method: bool
            If true, get the current method from instrument. If doing multiple
            things that use the current method status in a row, it can be useful
            to set this to false for some cases, may be faster.
        """
        if update_method:
            self.get_current_method_from_instrument()

        vals = self.get_pump_method_values(['Flow'], pump_id)

        try:
            flow_rate = float(vals['Flow'])
        except Exception:
            flow_rate = -1

        if flow_rate != -1:
            flow_rate = self._convert_flow_rate(flow_rate, self._flow_base_units,
                self._flow_units)

        return flow_rate

    def get_flow_accel(self, pump_id=None, update_method=True):
        """
        This returns the flow acceleration of the currently running method
        for the specified pump. If no pump is specified, the first pump
        in the pumps list is used. Note that this will replace the loaded
        method with the method on the instrument.

        Returns
        -------
        flow_accel: float
            The flow acceleration in the HPLC's specified flow_units. -1 is
            returned if flow acceleration cannot be acquired.
        update_method: bool
            If true, get the current method from instrument. If doing multiple
            things that use the current method status in a row, it can be useful
            to set this to false for some cases, may be faster.
        """
        if update_method:
            self.get_current_method_from_instrument()

        vals = self.get_pump_method_values(['MaximumFlowRamp'], pump_id)

        try:
            flow_accel = float(vals['MaximumFlowRamp'])
        except Exception:
            flow_accel = -1

        if flow_accel != -1:
            flow_accel = self._convert_flow_accel(flow_accel, self._flow_base_units,
                self._flow_units)

        return flow_accel

    def get_high_pressure_limit(self, pump_id=None, update_method=True):
        """
        This returns the high pressure limit of the currently running method
        for the specified pump. If no pump is specified, the first pump
        in the pumps list is used. Note that this will replace the loaded
        method with the method on the instrument.

        Returns
        -------
        pressure: float
            The high pressure limit in the HPLC's specified flow_units. -1 is
            returned if high pressure limit cannot be acquired.
        update_method: bool
            If true, get the current method from instrument. If doing multiple
            things that use the current method status in a row, it can be useful
            to set this to false for some cases, may be faster.
        """
        if update_method:
            self.get_current_method_from_instrument()

        vals = self.get_pump_method_values(['HighPressureLimit'], pump_id)

        try:
            pressure = float(vals['HighPressureLimit'])
        except Exception:
            pressure = -1

        if pressure != -1:
            pressure = self._convert_pressure(pressure, self._pressure_base_units,
                self._pressure_units)

        return pressure

    def get_pump_current_bottle_filling(self, bottle_list=None, pump_id=None):
        """
        Returns the specified bottle fillings for the specified pump. If no
        pump is specified, the first pump in the pumps list is used. Note that this
        is very slow (~1-2 s) and seems to cache (so sometimes will seem fast).
        Probably better to go through the data traces.

        Parameters
        ----------
        bottle_list: list
            A list of integers corresponding to bottles 1-4 to be returned.
            If no signal list is specified all 4 bottles are returned.
            For example, passing a bottle_list of [1, 3] would return
            bottles 1 and 3.

        uv_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        bottle_dict: dict
            A dictionary where the keys are the bottle number and the
            values are the current filling in L. Returns an empty dictionary
            if current bottle fillings cannot be acquired.
        """

        pump_id, success = self._inner_get_pump_property(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump max bottle fillings '
                'due to invalid pump id'), self.name)

        if not success:
            return {}

        if bottle_list is None:
            bottle_list = range(1,5)
        else:
            for val in bottle_list:
                if val != int(val) or val < 1 or val > 4:
                    logger.error(('One or more of the provided bottles '
                        'for HPLC %s pump %s is out of range (should be '
                        'between 1-4, so cannot get current bottle '
                        'fillings'), self.name, pump_id)
                    return {}

        bottle_dict = {}

        for val in bottle_list:
            if val == 1:
                bottle_id = 'BottleFilling_CurrentAbsolute'
            else:
                bottle_id = 'BottleFilling{}_CurrentAbsolute'.format(val)

            try:
                signal = float(self._pump_data[pump_id][bottle_id])
                bottle_dict[val] = signal
            except Exception:
                bottle_dict = {}
                break

        return bottle_dict

    def get_pump_max_bottle_filling(self, bottle_list=None, pump_id=None):
        """
        Returns the specified maximum bottle fillings for the specified pump.
        If no pump is specified, the first pump in the pumps list is used.

        Parameters
        ----------
        bottle_list: list
            A list of integers corresponding to bottles 1-4 to be returned.
            If no signal list is specified all 4 bottles are returned.
            For example, passing a bottle_list of [1, 3] would return
            bottles 1 and 3.

        uv_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        bottle_dict: dict
            A dictionary where the keys are the bottle number and the
            values are the maximum filling in L. Returns an empty dictionary
            if maximum bottle fillings cannot be acquired.
        """

        pump_id, success = self._inner_get_pump_property(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump max bottle filling '
                'due to invalid pump id'), self.name)

        if not success:
            return {}

        if bottle_list is None:
            bottle_list = range(1,5)
        else:
            for val in bottle_list:
                if val != int(val) or val < 1 or val > 4:
                    logger.error(('One or more of the provided bottles '
                        'for HPLC %s pump %s is out of range (should be '
                        'between 1-4, so cannot get maximum bottle '
                        'fillings'), self.name, pump_id)
                    return {}

        bottle_dict = {}

        for val in bottle_list:
            if val == 1:
                bottle_id = 'BottleFilling_MaximumAbsolute'
            else:
                bottle_id = 'BottleFilling{}_MaximumAbsolute'.format(val)

            try:
                signal = float(self._pump_data[pump_id][bottle_id])
                bottle_dict[val] = signal
            except Exception:
                bottle_dict = {}
                break

        return bottle_dict

    def get_pump_power_status(self, pump_id=None):
        """
        Returns the pump power status for the specified pump. If no pump is
        specified, the first pump in the pumps list is used.

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        power: str
            The power status of the pump, either 'On', 'Off', or 'Standby'.
            Returns an empty string if status cannot be acquired.
        """

        pump_id, success = self._inner_get_pump_property(pump_id)

        if not success:
            logger.error(('Failed to get HPLC %s pump power status due to '
                'invalid pump id'), self.name)

        if not success:
            return ''

        try:
            power = self._pump_data[pump_id]['PumpPower']
        except Exception:
            power = ''

        return power

    def get_autosampler_temperature(self, as_id=None):
        """
        Returns the autosampler thermostat temperature for the specified
        autosampler. If no autosampler is specified, the first autosampler
        in the autosamplers list is used. Note that this is very slow (~1-2 s)
        and seems to cache (so sometimes will seem fast). Probably better
        to go through the data traces.

        Parameters
        ----------
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        temperature: float
            The temperature in C. -1 is returned if temperature cannot be
            acquired.
        """
        as_id, success = self._inner_get_autosampler_property(as_id)

        if not success:
            logger.error(('Failed to get HPLC %s autosampler temperature due to '
                'invalid autosampler id'), self.name)

        if not success:
            return -1

        try:
            temp = float(self._autosampler_data[as_id]['Thermostat_Temperature'])
        except Exception:
            temp = -1

        return temp

    def get_autosampler_thermostat_power_status(self, as_id=None):
        """
        Returns the autosampler thermostat power status for the specified
        autosampler. If no autosampler is specified, the first autosampler
        in the autosamplers list is used.

        Parameters
        ----------
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        power: str
            The thermostat power status of the autosampler, either 'On' or
            'Off'. Returns an empty string if status cannot be acquired.
        """

        as_id, success = self._inner_get_autosampler_property(as_id)

        if not success:
            logger.error(('Failed to get HPLC %s autosampler thermostat power '
                'status due to invalid autosampler id'), self.name)

        if not success:
            return ''

        try:
            power = self._autosampler_data[as_id]['Thermostat_PowerOn']
        except Exception:
            power = ''

        if power == 'True':
            power = 'On'
        elif power == 'False':
            power = 'Off'

        return power

    def get_mwd_absorbance(self, signal_list=None, uv_id=None):
        """
        Returns the specified absorbance signals for the specified
        multiwavelength detector (MWD). If no detector is specified,
        the first detector in the uvs list is used.

        Parameters
        ----------
        signal_list: list
            A list of integers corresponding to signals 1-8 to be returned.
            If no signal list is specified all 8 signals are returned.
            For example, passing a signal_list of [1, 3, 5] would return
            signals 1, 3, and 5.

        uv_id: str
            The OpenLab CDS Hashkey for the uv detector module.

        Returns
        -------
        absorbance: dict
            A dictionary where the keys are the signal number and the
            values are the absorbance in mAu. Returns an empty dictionary
            if signals cannot be acquired.
        """

        uv_id, success = self._inner_get_uv_property(uv_id)

        if not success:
            logger.error(('Failed to get HPLC %s detector absorbance  due '
                'to invalid detector id'), self.name)

        if not success:
            return {}

        if signal_list is None:
            signal_list = range(1,9)
        else:
            for val in signal_list:
                if val != int(val) or val < 1 or val > 8:
                    logger.error(('One or more of the provided signals '
                        'for HPLC %s MWD %s is out of range (should be '
                        'between 1-8, so cannot get absorbance'), self.name,
                        uv_id)
                    return {}

        signal_dict = {}

        for val in signal_list:
            if val == 1:
                signal_id = 'Signal_Current'
            else:
                signal_id = 'Signal{}_Current'.format(val)

            try:
                signal = float(self._uv_data[uv_id][signal_id])
                signal_dict[val] = signal
            except Exception:
                signal_dict = {}
                break

        return signal_dict

    def get_uv_lamp_power_status(self, uv_id=None):
        """
        Returns the uv lamp power status for the specified detector. If no
        detector is specified, the first detector in the uvs list is used.

        Parameters
        ----------
        uv_id: str
            The OpenLab CDS Hashkey for the uv detector module.

        Returns
        -------
        power: str
            The power status of the uv lamp, either 'On' or 'Off'.
            Returns an empty string if status cannot be acquired.
        """

        uv_id, success = self._inner_get_uv_property(uv_id)

        if not success:
            logger.error(('Failed to get HPLC %s detector uv lamp status due '
                'to invalid detector id'), self.name)

        if not success:
            return ''

        try:
            power = self._uv_data[uv_id]['UVLampState']
        except Exception:
            power = ''

        return power

    def get_vis_lamp_power_status(self, uv_id=None):
        """
        Returns the uv lamp power status for the specified detector. If no
        detector is specified, the first detector in the uvs list is used.

        Parameters
        ----------
        uv_id: str
            The OpenLab CDS Hashkey for the uv detector module.

        Returns
        -------
        power: str
            The power status of the uv lamp, either 'On' or 'Off'.
            Returns an empty string if status cannot be acquired.
        """

        uv_id, success = self._inner_get_uv_property(uv_id)

        if not success:
            logger.error(('Failed to get HPLC %s detector visible lamp status '
                'due to invalid detector id'), self.name)

        if not success:
            return ''

        try:
            power = self._uv_data[uv_id]['IsVisLampOn']
        except Exception:
            power = ''

        if power == 'True':
            power = 'On'
        elif power == 'False':
            power = 'Off'

        return power

    def get_connected(self):
        """
        Returns the instrument connected state.

        Returns
        -------
        connected: bool
            True if the instrument is connected, False otherwise.
        """
        return copy.copy(self._connected)

    def remove_runs_from_queue(self, names):
        """
        Removes the runs from the run queue. Run status must be pending in
        order for it to be removed.

        Parameters
        ----------
        names: list
            A list of run names to be removed.
        """
        remove_list = List[Guid]()
        fail_list = []

        for name in names:
            status = self.get_run_status(name)

            if status == 'Pending':
                guid = self._run_data[name]['guid']

                remove_list.Add(guid)

            else:
                fail_list.append(name)

        if len(remove_list) > 0:
            self.controller.DeleteRunItems(remove_list)

        if len(fail_list) > 0:
            logger.error(('HPLC %s runs %s were not removed from the run '
                'queue because their status was not pending.'), self.name,
                ', '.join(fail_list))


    def set_data_trace_max_length(self, trace_length):
        """
        Sets the maximum length of a data trace. For example, if the value
        is set to 120 (the default), 120 minutes worth of data are kept,
        and as new data is acquired older data will be dropped.

        Parameters
        ----------
        trace_length: float
            The maximum length of a data trace preserved in software in
            minutes.
        """
        with self._trace_lock:
           self._trace_history_length = float(trace_length)

    def set_pump_on(self, pump_id=None):
        """
        Turns the specified pump on. If no pump is specified, the first pump
        in the pumps list is used. Note that this requires the ability to take
        control of the instrument. If you also have the OpenLab CDS Acquisition
        GUI open you'll have to Release control (upper left corner of the window).

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        success: bool
            True if successful.
        """
        pump_id, success = self._validate_pump_id(pump_id)

        if not success:
            logger.error(('Failed to set HPLC %s pump on due to an '
                'invalid pump id'), self.name)
            set_success = False

        else:
            state = self.get_pump_power_status(pump_id)

            if state != 'On':
                states = Dictionary[String, DeviceStatesEnum]()
                states[pump_id] = DeviceStatesEnum.On

                control = self.controller.TakeInstrumentControl()
                try:
                    if (control.TakeControlReturnCode.ToString() == 'OK' or
                        control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                        self.controller.SetDevicesNewStates(states)

                        logger.info('Turned HPLC %s pump %s on', self.name, pump_id)
                        set_success = True

                    else:
                        logger.error('Could not acquire control of the device, '
                            'failed to turn HPLC %s pump %s on', self.name,
                            pump_id)
                        set_success = False

                except Exception:
                    logger.error('Failed to turn HPLC %s pump %s on', self.name,
                        pump_id)
                    set_success = False
                finally:
                    control.Dispose()

            else:
                logger.info('HPLC %s pump %s already on', self.name, pump_id)
                set_success = True

        return set_success

    def set_pump_standby(self, pump_id=None):
        """
        Turns the specified pump to standby. If no pump is specified, the first pump
        in the pumps list is used. Note that this requires the ability to take
        control of the instrument. If you also have the OpenLab CDS Acquisition
        GUI open you'll have to Release control (upper left corner of the window).

        Parameters
        ----------
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns: bool
            True if successful
        """
        pump_id, success = self._validate_pump_id(pump_id)

        if not success:
            logger.error(('Failed to set HPLC %s pump to standby due to an '
                'invalid pump id'), self.name)
            set_success = False

        else:
            state = self.get_pump_power_status(pump_id)

            if state != 'Standby':
                states = Dictionary[String, DeviceStatesEnum]()
                states[pump_id] = DeviceStatesEnum.Standby

                control = self.controller.TakeInstrumentControl()
                try:
                    if (control.TakeControlReturnCode.ToString() == 'OK' or
                        control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                        self.controller.SetDevicesNewStates(states)

                        logger.info('Set HPLC %s pump %s to standby', self.name,
                            pump_id)
                        set_success = True

                    else:
                        logger.error('Could not acquire control of the device, '
                            'failed to set HPLC %s pump %s to standby', self.name,
                            pump_id)
                        set_success = False

                except Exception:
                    logger.error('Failed to set HPLC %s pump %s to standby',
                        self.name, pump_id)
                    set_success = False

                finally:
                    control.Dispose()
            else:
                logger.info('HPLC %s pump %s already in standby', self.name, pump_id)
                set_success = True

        return set_success

    def set_autosampler_on(self, as_id=None):
        """
        Turns the specified autosampler on. If no autosampler is specified,
        the first autosampler in the autosamplers list is used. Note that
        this requires the ability to take control of the instrument. If you
        also have the OpenLab CDS Acquisition GUI open you'll have to
        Release control (upper left corner of the window).

        Parameters
        ----------
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        success: bool
            True if successful.
        """
        as_id, success = self._validate_as_id(as_id)

        if not success:
            logger.error(('Failed to set HPLC %s autosampler on due to an '
                'invalid autosampler id'), self.name)
            set_success = False

        else:
            # state = self.get_pump_power_status(as_id) #Don't know how to do this yet
            state = '?'

            if state != 'On':
                states = Dictionary[String, DeviceStatesEnum]()
                states[as_id] = DeviceStatesEnum.On

                control = self.controller.TakeInstrumentControl()
                try:
                    if (control.TakeControlReturnCode.ToString() == 'OK' or
                        control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                        self.controller.SetDevicesNewStates(states)

                        logger.info('Turned HPLC %s autosampler %s on', self.name,
                            as_id)
                        set_success = True

                    else:
                        logger.error('Could not acquire control of the device, '
                            'failed to turn HPLC %s autosampler %s on', self.name,
                            as_id)
                        set_success = False

                except Exception:
                    logger.error('Failed to turn HPLC %s autosampler %s on',
                        self.name, as_id)
                    set_success = False
                finally:
                    control.Dispose()

            else:
                logger.info('HPLC %s autosampler %s already on', self.name, as_id)
                set_success = True

        return set_success

    def set_uv_on(self, uv_id=None):
        """
        Turns the specified detector on. If no detector is specified,
        the first detector in the detectors list is used. Note that
        this requires the ability to take control of the instrument. If you
        also have the OpenLab CDS Acquisition GUI open you'll have to
        Release control (upper left corner of the window).

        Parameters
        ----------
        uv_id: str
            The OpenLab CDS Hashkey for the detector module.

        Returns
        -------
        success: bool
            True if successful.
        """
        uv_id, success = self._validate_uv_id(uv_id)

        if not success:
            logger.error(('Failed to set HPLC %s uv detector on due to an '
                'invalid uv id'), self.name)
            set_success = False

        else:
            # state = self.get_pump_power_status(uv_id) #Don't know how to do this yet
            state = '?'

            if state != 'On':
                states = Dictionary[String, DeviceStatesEnum]()
                states[uv_id] = DeviceStatesEnum.On
                print(f"this is states {states}")

                control = self.controller.TakeInstrumentControl()
                try:
                    if (control.TakeControlReturnCode.ToString() == 'OK' or
                        control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                        self.controller.SetDevicesNewStates(states)

                        logger.info('Turned HPLC %s detector %s on', self.name,
                            uv_id)
                        set_success = True

                    else:
                        logger.error('Could not acquire control of the device, '
                            'failed to turn HPLC %s detector %s on', self.name,
                            uv_id)
                        set_success = False

                except Exception:
                    logger.error('Failed to turn HPLC %s detector %s on',
                        self.name, uv_id)
                    set_success = False

                finally:
                    control.Dispose()

            else:
                logger.info('HPLC %s detector %s already on', self.name, uv_id)
                set_success = True

        return set_success
    def set_uv_off(self, uv_id=None):
        """
        Turns the specified detector off. If no detector is specified,
        the first detector in the detectors list is used. Note that
        this requires the ability to take control of the instrument. If you
        also have the OpenLab CDS Acquisition GUI open you'll have to
        Release control (upper left corner of the window).

        Parameters
        ----------
        uv_id: str
            The OpenLab CDS Hashkey for the detector module.

        Returns
        -------
        success: bool
            True if successful.
        """
        uv_id, success = self._validate_uv_id(uv_id)

        if not success:
            logger.error(('Failed to set HPLC %s uv detector off due to an '
                'invalid uv id'), self.name)
            set_success = False

        else:
            # state = self.get_pump_power_status(uv_id) #Don't know how to do this yet
            state = '?'

            if state != 'Standby':
                states = Dictionary[String, DeviceStatesEnum]()
                states[uv_id] = DeviceStatesEnum.Standby
                print(f"this is states {states}")

                control = self.controller.TakeInstrumentControl()
                try:
                    if (control.TakeControlReturnCode.ToString() == 'OK' or
                        control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                        self.controller.SetDevicesNewStates(states)

                        logger.info('Turned HPLC %s detector %s on', self.name,
                            uv_id)
                        set_success = True

                    else:
                        logger.error('Could not acquire control of the device, '
                            'failed to turn HPLC %s detector %s off', self.name,
                            uv_id)
                        set_success = False

                except Exception:
                    logger.error('Failed to turn HPLC %s detector %s off',
                        self.name, uv_id)
                    set_success = False

                finally:
                    control.Dispose()

            else:
                logger.info('HPLC %s detector %s already off', self.name, uv_id)
                set_success = True

        return set_success

    def set_sample_prep_method_values(self, method_vals, as_id=None):
        """
        Sets the values of autosampler method. Note that this sets the values for
        whatever method you have currently loaded into this AgilentHPLC object.
        It will not save the method or send the values to the controller.
        Note that if a value is set to automatic or off (e.g. 'PostTime_Mode'
        is 'Off') then trying to set the corresponding value (e.g. 'PostTime_Time')
        will fail. Additionally, passing in complex objects (e.g. the autosampler
        'TimeTable') seems to result in an error.  Also note that you have to
        pass the correct type, and you may have to use a C# object instead of
        the python object to make it work. Where this is known, conversion is
        done  automatically. If no autosampler is specified, the first
        autosampler in the autosamplers list is used.

        Parameters
        ----------
        method_ids: list
            A dictionary of method values where the key is the method id
            and the value is the value to be set. The method ids can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_sample_prep_method_ids` method.
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        success: bool
            Returns True if all values are successful set. Otherwise False.
        """
        as_id, success = self._validate_as_id(as_id)

        if not success:
            logger.error(('Failed to set HPLC %s sample prep method values '
                'due to an invalid autosampler id'), self.name)
            success = False

        else:
            prop_val_list = []

            for key, value in method_vals.items():
                prop_val = ResourceIdAndValue()
                prop_val.PropertyId = key

                if isinstance(value, int) and not isinstance(value, bool):
                    value = Int32(value)

                prop_val.PropertyValue = value
                prop_val_list.append(prop_val)

            res = self.controller.SetSamplePrepMethodResourceProperties(as_id,
                prop_val_list)

            success = True

            errors = ''
            val_keys = list(method_vals.keys())
            for i in range(len(res[1])):
                item = res[1][i]
                res_str = item.Result.ToString()
                if res_str != 'OK':
                    success = False
                    errors += '{}: {}\n'.format(val_keys[i], res_str)

            if not success:
                logger.error(("Failed to set HPLC %s sample prep method values:\n"
                    +errors), self.name)

        return success

    def set_pump_method_values(self, method_vals, pump_id=None):
        """
        Sets the values of pump method. Note that this sets the values for
        whatever method you have currently loaded into this AgilentHPLC object.
        It will not save the method or send the values to the controller.
        Note that if a value is set to automatic or off (e.g. 'PostTime_Mode'
        is 'Off') then trying to set the corresponding value (e.g. 'PostTime_Time')
        will fail. Additionally, passing in complex objects (e.g. the pump
        'TimeTable') seems to result in an error.  Also note that you have to
        pass the correct type, and you may have to use a C# object instead of
        the python object to make it work. Where this is known, conversion is
        done  automatically. If no pump is specified, the first pump in the
        pumps list is used.

        Parameters
        ----------
        method_ids: list
            A dictionary of method values where the key is the method id
            and the value is the value to be set. The method ids can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_pump_method_ids` method.
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        success: bool
            Returns True if all values are successful set. Otherwise False.
        """
        pump_id, success = self._validate_pump_id(pump_id)

        if not success:
            logger.error(('Failed to set HPLC %s pump method values due to an '
                'invalid pump id'), self.name)
            success = False

        else:
            prop_val_list = []
            for key, value in method_vals.items():
                prop_val = ResourceIdAndValue()
                prop_val.PropertyId = key

                if isinstance(value, int) and not isinstance(value, bool):
                    value = Int32(value)

                prop_val.PropertyValue = value
                prop_val_list.append(prop_val)

            res = self.controller.SetMethodResourceProperties(pump_id,
                prop_val_list)

            success = True

            errors = ''
            val_keys = list(method_vals.keys())
            for i in range(len(res[1])):
                item = res[1][i]
                res_str = item.Result.ToString()
                if res_str != 'OK':
                    success = False
                    errors += '{}: {}\n'.format(val_keys[i], res_str)

            if not success:
                logger.error(("Failed to set HPLC %s pump method values:\n"
                    +errors), self.name)

        return success

    def set_autosampler_method_values(self, method_vals, as_id=None):
        """
        Sets the values of autosampler method. Note that this sets the values for
        whatever method you have currently loaded into this AgilentHPLC object.
        It will not save the method or send the values to the controller.
        Note that if a value is set to automatic or off (e.g. 'StopTime_Mode'
        is 'Off') then trying to set the corresponding value (e.g. 'StopTime_Time')
        will fail. Additionally, passing in complex objects seems to result
        in an error. Also note that you have to pass the correct
        type, and you may have to use a C# object instead of the python
        object to make it work. Where this is known, conversion is done
        automatically. If no autosampler is specified, the first
        autosampler in the autosamplers list is used.

        Parameters
        ----------
        method_ids: list
            A dictionary of method values where the key is the method id
            and the value is the value to be set. The method ids can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_autosampler_method_ids` method.
        as_id: str
            The OpenLab CDS Hashkey for the autosampler module.

        Returns
        -------
        success: bool
            Returns True if all values are successful set. Otherwise False.
        """
        as_id, success = self._validate_as_id(as_id)

        if not success:
            logger.error(('Failed to set HPLC %s autosampler method values '
                'due to an invalid autosampler id'), self.name)
            success = False

        else:
            prop_val_list = []
            for key, value in method_vals.items():
                prop_val = ResourceIdAndValue()
                prop_val.PropertyId = key

                if isinstance(value, int) and not isinstance(value, bool):
                    value = Int32(value)

                prop_val.PropertyValue = value
                prop_val_list.append(prop_val)

            res = self.controller.SetMethodResourceProperties(as_id,
                prop_val_list)

            success = True

            errors = ''
            val_keys = list(method_vals.keys())
            for i in range(len(res[1])):
                item = res[1][i]
                res_str = item.Result.ToString()
                if res_str != 'OK':
                    success = False
                    errors += '{}: {}\n'.format(val_keys[i], res_str)

            if not success:
                logger.error(("Failed to set HPLC %s autosampler method values:\n"
                    +errors), self.name)

        return success

    def set_uv_method_values(self, method_vals, uv_id=None):
        """
        Sets the values of uv detector method. Note that this sets the values for
        whatever method you have currently loaded into this AgilentHPLC object.
        It will not save the method or send the values to the controller.
        Note that if a value is set to automatic or off (e.g. 'PostTime_Mode'
        is 'Off') then trying to set the corresponding value (e.g. 'PostTime_Time')
        will fail. Additionally, passing in complex objects (e.g. the uv
        'TimeTable') seems to result in an error.  Also note that you have to
        pass the correct type, and you may have to use a C# object instead of
        the python object to make it work. Where this is known, conversion is
        done  automatically. If no uv is specified, the first uv in the
        uvs list is used.

        Parameters
        ----------
        method_ids: list
            A dictionary of method values where the key is the method id
            and the value is the value to be set. The method ids can
            be obtained from the
            :py:meth:`agilentcon.hplccon.AgilentHPLC.get_all_uv_method_ids` method.
        uv_id: str
            The OpenLab CDS Hashkey for the detector module.

        Returns
        -------
        success: bool
            Returns True if all values are successful set. Otherwise False.
        """
        uv_id, success = self._validate_uv_id(uv_id)

        if not success:
            logger.error(('Failed to set HPLC %s uv method values due to an '
                'invalid uv id'), self.name)
            success = False

        else:
            prop_val_list = []
            for key, value in method_vals.items():
                prop_val = ResourceIdAndValue()
                prop_val.PropertyId = key

                if isinstance(value, int) and not isinstance(value, bool):
                    value = Int32(value)

                prop_val.PropertyValue = value
                prop_val_list.append(prop_val)

            res = self.controller.SetMethodResourceProperties(uv_id,
                prop_val_list)

            success = True

            errors = ''
            val_keys = list(method_vals.keys())
            for i in range(len(res[1])):
                item = res[1][i]
                res_str = item.Result.ToString()
                if res_str != 'OK':
                    success = False
                    errors += '{}: {}\n'.format(val_keys[i], res_str)

            if not success:
                logger.error(("Failed to set HPLC %s uv method values:\n"
                    +errors), self.name)

        return success

    def save_current_method(self, save_name=None, overwrite=True):
        """
        Saves current method. If no save_name is specified, the current method
        is saved with the same name. If the current method is from the
        instrument it has no name, so the method is saved as 'python_inst.amx'
        unless otherwise specified.

        Parameters
        ----------
        save_name: str
            The save name for the method. Should include any path relative
            to the base OpenLab CDS Methods directory.
        overwrite: bool
            If a method of the same name exists, should it be overwritten.
            Default is True.
        """
        if self._current_method == 'instrument' and save_name is None:
            save_name = 'python_inst.amx'

        if save_name is not None:
            method_path, rel_base_path = self._normalize_method_path(save_name,
                'acq')

            rel_method_path = os.path.join(rel_base_path,
                os.path.split(method_path)[1])

        if (self._current_method == 'instrument' or (save_name is not None
                and rel_method_path != self._current_method)):
            exists = os.path.exists(method_path)

            if exists and overwrite:
                os.remove(method_path)
                exists = False
            elif exists and not overwrite:
                logger.error(('HPLC %s cannot write method, method already '
                    'exists'), self.name)

            if not exists:
                self.controller.SaveAsAcquisitionMethodNoOverwrite(method_path,
                    'Saving method')

        else:
            self.controller.SaveAcquisitionMethod('Saving method')

    def save_current_sample_prep_method(self, save_name=None, overwrite=True):
        """
        Saves current sample prep method. If no save_name is specified, the
        current method is saved with the same name.

        Parameters
        ----------
        save_name: str
            The save name for the method. Should include any path relative
            to the base OpenLab CDS Methods directory.
        overwrite: bool
            If a method of the same name exists, should it be overwritten.
            Default is True.
        """
        if save_name is not None:
            method_path, rel_base_path = self._normalize_method_path(save_name,
                'sample')

            rel_method_path = os.path.join(rel_base_path,
                os.path.split(method_path)[1])

        if (save_name is not None
            and rel_method_path != self._current_sample_prep_method):
            exists = os.path.exists(method_path)

            if exists and overwrite:
                os.remove(method_path)
                exists = False
            elif exists and not overwrite:
                logger.error(('HPLC %s cannot write method, method already '
                    'exists'), self.name)

            if not exists:
                self.controller.SaveAsSamplePrepMethodNoOverwrite(method_path,
                    'Saving method')

        else:
            self.controller.SaveSamplePrepMethod('Saving method')

    def send_current_method_to_instrument(self):
        """
        Sends whatever method is loaded to the instrument. The method will
        be saved first, either with the current method name or as
        'python_inst.amx' if the method has no name.  Note that
        this requires the ability to take control of the instrument. If you
        also have the OpenLab CDS Acquisition GUI open you'll have to
        Release control (upper left corner of the window).

        Returns
        -------
        success: bool
            True if successful.
        """
        self.save_current_method()

        success = True

        if self._current_method == 'instrument':
            save_name = 'python_inst.amx'
        else:
            save_name = self._current_method

        method_path = os.path.join(self._project_path, 'Methods', save_name)
        method_path = os.path.abspath(os.path.expanduser(method_path))

        control = self.controller.TakeInstrumentControl()
        try:
            if (control.TakeControlReturnCode.ToString() == 'OK' or
                control.TakeControlReturnCode.ToString() == 'AlreadyHaveControl'):
                self.controller.DownloadMethod(method_path, True)

                logger.debug(('HPCL %s sent current method to instrument.'),
                    self.name)
            else:
                logger.error('Could not acquire control of the device, '
                    'HPLC %s failed to send current method to instrument.',
                    self.name)
                success = False

        except Exception:
            logger.error('Failed to send HPLC %s current method to instrument',
                self.name)
            success = False
        finally:
            control.Dispose()

        return success

    def set_flow_rate(self, flow_rate, pump_id=None):
        """
        A convenience method to set the current flow rate. It loads the
        method from the instrument, updates the flow rate to the target
        flow rate, and then sends the method back to the instrument. If
        no pump is specified, the first pump in the pumps list is used.
        Note that this method converts between the flow units set for the hplc
        object and the base units of the instrument. If flow rate is set
        via the general method parameters setting no such unit conversion
        takes place.

        Parameters
        ----------
        flow_rate: float
            The flow rate to be set.
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        success: bool
            True if successful.

        """
        pump_id, success = self._inner_get_pump_property(pump_id)

        try:
            flow_rate = float(flow_rate)
        except Exception:
            flow_rate = None

        if flow_rate is not None:
            flow_rate = self._convert_flow_rate(flow_rate, self._flow_units,
                self._flow_base_units)

            if success:
                self.get_current_method_from_instrument()
                self.set_pump_method_values({'Flow': flow_rate}, pump_id)
                set_success = self.send_current_method_to_instrument()
            else:
                logger.error(('Failed to set HPLC %s pump flow rate due to '
                    'invalid pump id'), self.name)
                set_success = False
        else:
            logger.error(('Failed to set HPLC %s pump flow rate. Provided '
                'rate was not a number'), self.name)
            set_success = False

        return set_success

    def set_flow_accel(self, flow_accel, pump_id=None):
        """
        A convenience method to set the current flow acceleration. It
        loads the method from the instrument, updates the flow
        acceleration to the target flow acceleration, and then sends the
        method back to the instrument. If no pump is specified, the first
        pump in the pumps list is used. Note that this method converts
        between the flow units set for the hplc object and the base units
        of the instrument. If flow rate is set via the general method
        parameters setting no such unit conversion takes place.

        Parameters
        ----------
        flow_accel: float
            The flow acceleration to be set.
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        success: bool
            True if successful.
        """
        pump_id, success = self._inner_get_pump_property(pump_id)

        try:
            flow_accel = float(flow_accel)
        except Exception:
            flow_accel = None

        if flow_accel is not None:
            flow_accel = self._convert_flow_accel(flow_accel, self._flow_units,
                self._flow_base_units)

            if success:
                self.get_current_method_from_instrument()
                self.set_pump_method_values({'MaximumFlowRamp': flow_accel},
                    pump_id)
                set_success = self.send_current_method_to_instrument()
            else:
                logger.error(('Failed to set HPLC %s pump flow rate due to '
                    'invalid pump id'), self.name)
                set_success = False

        else:
            logger.error(('Failed to set HPLC %s pump flow accel. Provided '
                'acceleration was not a number'), self.name)
            set_success = False

        return set_success

    def set_high_pressure_limit(self, pressure, pump_id=None):
        """
        A convenience method to set the current high pressure limit. It loads
        the method from the instrument, updates the limit to the target
        pressure, and then sends the method back to the instrument. If
        no pump is specified, the first pump in the pumps list is used.
        Note that this method converts between the pressure units set for
        the hplc object and the base units of the instrument. If the
        pressure limit is set via the general method parameters setting no
        such unit conversion takes place.

        Parameters
        ----------
        pressure: float
            The high pressure limit to be set.
        pump_id: str
            The OpenLab CDS Hashkey for the pump module.

        Returns
        -------
        success: bool
            True if successful.

        """
        pump_id, success = self._inner_get_pump_property(pump_id)

        try:
            pressure = float(pressure)
        except Exception:
            pressure = None

        if pressure is not None:
            pressure = self._convert_pressure(pressure, self._flow_units,
                self._flow_base_units)

            if success:
                self.get_current_method_from_instrument()
                self.set_pump_method_values({'HighPressureLimit': pressure},
                    pump_id)
                set_success = self.send_current_method_to_instrument()
            else:
                logger.error(('Failed to set HPLC %s pump high pressure limit '
                    'due to invalid pump id'), self.name)
                set_success = False
        else:
            logger.error(('Failed to set HPLC %s pump high pressure limit. '
                'Provided pressure was not a number'), self.name)
            set_success = False

        return set_success

    def submit_single_sample(self, name, sample_params, result_path=None,
        result_name=None):
        """
        Submits a single sample from the autosampler. Note that you seem to
        need at least ~1 s between submitting single samples or you will
        get an error. If you need to submit a large batch all at once better
        to use a sequence.

        Parameters
        ----------
        name: str
            Name for the submitted run. Can be used to get information
            about the run status. Note that if the name is the same as the
            name of another sample, you will only be able to retrieve
            information on the most recent sample with that name.

        sample_params: dict
            A dictionary of the sample parameters. It must contain:

            *   Required: 'acq_method' - The acquisition method to be used.
                The path should be relative to to the top level Methods
                folder
            *   Required: 'sample_loc' - The sample location in the autosampler
                (e.g. D1F-A1 being drawer 1 front, position A1)
            *   Optional: 'sample_name' - The sample name
            *   Optional: 'proc_method' - The processing method to be used
            *   Optional: 'injection_vol' - Injection volume (not passing this
                uses the method volume). Float.
            *   Optional: 'sample_descrip' - The sample description
            *   Optional: 'is_priority' - Sets if the sample is a priority sample.
                Boolean.
            *   Optional: 'sample_type' - Sample type. Must be one of: 'Sample',
                'Calibration', 'Blank', 'DoubleBlank', 'QCCheck', 'Spike',
                'SystemSuitability'
            *   Optional: 'sp_method' - Sample prep method to be used.
                The path should be relative to the top level Methods
                folder

        result_path: str
            The path to save the result in, relative to the project base
            results path. If no path is provided, the base results path will
            be used.

        result_name: str
            The filename for the result. If no name is provided, the default
            name (date and time) will be used.

        Returns
        -------
        success: bool
        """

        if name in self._run_data:
            logger.warning('Run name %s already exists on HPLC %s', name, self.name)

        acq_method = sample_params['acq_method']
        sample_loc = sample_params['sample_loc']
        proc_method = sample_params['proc_method']

        method_path, rel_base_path = self._normalize_method_path(acq_method,
            'acq')
        proc_method_path, rel_base_path = self._normalize_method_path(proc_method,
            'proc')

        if result_path is not None:
            result_path = os.path.join(self._project_path, 'Results', result_path)
        else:
            result_path = os.path.join(self._project_path, 'Results')
        result_path = os.path.abspath(os.path.expanduser(result_path))

        single_run_params = SingleRunParams()

        single_run_params.AcquisitionMethod = method_path
        single_run_params.ProcessingMethod = proc_method_path
        single_run_params.SampleLocation = sample_loc
        single_run_params.SelectedInjection = self.injection_devices[self.inj_source]
        single_run_params.ResultPath = result_path

        if 'injection_vol' in sample_params:
            injection_vol = float(sample_params['injection_vol'])
            single_run_params.InjectionVolume = injection_vol

        if result_name is not None:
            single_run_params.ResultFilename = result_name

        if 'sample_name' in sample_params:
            sample_name = sample_params['sample_name']
            single_run_params.SampleName = sample_name

#        if 'proc_method' in sample_params:
#            proc_method = sample_params['proc_method']
#            single_run_params.ProcessingMethod = proc_method

        if 'sample_descrip' in sample_params:
            sample_descrip = sample_params['sample_descrip']
            single_run_params.SampleDescription = sample_descrip

        if 'is_priority' in sample_params:
            is_priority = sample_params['is_priority']
            single_run_params.IsPriority = is_priority

        if 'sample_type' in sample_params:
            sample_type = getattr(SampleType, sample_params['sample_type'])
            single_run_params.SampleType = sample_type

        if 'sp_method' in sample_params:
            sp_method = sample_params['sp_method']
            method_path, rel_base_path = self._normalize_method_path(sp_method,
                'sample')
            single_run_params.SamplePrepMethod = method_path

        try:
            with self._run_lock:
                self._run_data[name] = {
                    'status'            : '',
                    'run_id'            : '',
                    'guid'              : None,
                    'params'            : [sample_params],
                    'rtype'             : 'SingleRun',
                    'total_injections'  : 1,
                    'current_injection' : None,
                    'acq_method'        : [sample_params['acq_method'],],
                    }

            result = self.controller.SubmitSingleRun(single_run_params)
            success = True

            with self._run_lock:
                self._run_ids[result.RunId.ToString()] = name
                self._run_data[name]['run_id'] = result.RunId.ToString()
                self._run_data[name]['guid'] = result.RunId

            logger.info('Submitted a single sample to HPLC %s with parameters: %s',
                self.name, ', '.join(
                ['{}:{}'.format(kw, item) for kw, item in sample_params.items()]))

        except Exception:
            logger.error('Failed to submit sample to HPLC {}:\n{}'.format(
                self.name, traceback.format_exc()))
            success = False

        if success:
            with self._run_lock:
                self._run_queue.append(name)
        else:
            with self._run_lock:
                if name in self._run_data:
                    del self._run_data[name]

        return success

    def submit_sequence(self, name, sequence_list, result_path=None,
        result_name=None):
        """
        Submits a single sample from the autosampler

        Parameters
        ----------
        name: str
            Name for the submitted sequence. Can be used to get information
            about the run status. Note that if the name is the same as the
            name of another sample, you will only be able to retrieve
            information on the most recent sample.

        sequence_list: list
            A list where each entry is a dictionary dictionary of the sample
            parameters. Each sample dictionary may contain:

            *   Required: 'acq_method' - The acquisition method to be used.
                The path should be relative to to the top level Methods
                folder
            *   Required: 'sample_loc' - The sample location in the autosampler
                (e.g. D1F-A1 being drawer 1 front, position A1)
            *   Optional: 'result_name' - Item specific data file name
            *   Optional: 'sample_name' - The sample name
            *   Optional: 'proc_method' - The processing method to be used
            *   Optional: 'injection_vol' - Injection volume (not passing this
                uses the method volume). Float.
            *   Optional: 'sample_descrip' - The sample description
            *   Optional: 'sample_type' - Sample type. Must be one of: 'Sample',
                'Calibration', 'Blank', 'DoubleBlank', 'QCCheck', 'Spike',
                'SystemSuitability'
            *   Optional: 'num_injections' - Number of injections per
                sample. Int.
            *   Optional: 'sp_method' - Sample prep method to be used.
                The path should be relative to the top level Methods
                folder

        result_path: str
            The path to save the result in, relative to the project base
            results path. If no path is provided, the base results path will
            be used.

        result_name: str
            The filename for the result. If no name is provided, the default
            name (date and time) will be used.

        Returns
        -------
        success: bool
        """
        if name in self._run_data:
            logger.warning('Run name %s already exists on HPLC %s', name, self.name)

        seq_item_list = observable_collection[SequenceRecord]()
        acq_method_list = []

        for sample_params in sequence_list:
            acq_method = sample_params['acq_method']
            sample_loc = sample_params['sample_loc']

            if acq_method not in acq_method_list:
                acq_method_list.append(acq_method)

            method_path, rel_base_path = self._normalize_method_path(acq_method,
                'acq')

            seq_item = SequenceRecord()

            seq_item.AcquisitionMethodPath = method_path
            seq_item.SampleLocation = sample_loc
            seq_item.SelectedInjection = self.injection_devices[self.inj_source]

            if 'injection_vol' in sample_params:
                injection_vol = float(sample_params['injection_vol'])
                seq_item.InjectionVolume = injection_vol

            if 'result_name' in sample_params:
                result_name = sample_params['result_name']
                seq_item.DataFilename = result_name

            if 'sample_name' in sample_params:
                sample_name = sample_params['sample_name']
                seq_item.SampleName = sample_name

            if 'proc_method' in sample_params:
                proc_method = sample_params['proc_method']
                seq_item.ProcessingMethodPath = proc_method

            if 'sample_descrip' in sample_params:
                sample_descrip = sample_params['sample_descrip']
                seq_item.SampleDescription = sample_descrip

            if 'sample_type' in sample_params:
                sample_type = getattr(SampleType, sample_params['sample_type'])
                seq_item.SampleType = sample_type

            if 'num_injections' in sample_params:
                num_injections = int(sample_params['num_injections'])
                seq_item.InjectionsPerSample = num_injections

            if 'sp_method' in sample_params:
                sp_method = sample_params['sp_method']
                method_path, rel_base_path = self._normalize_method_path(sp_method,
                    'sample')
                seq_item.SamplePrepMethodPath = method_path

            seq_item_list.Add(seq_item)

        sequence = SequenceSet()
        sequence.SequenceType = getattr(SequenceSetType, 'None')
        sequence.SequenceRecordSet = seq_item_list

        if result_path is not None:
            result_path = os.path.join(self._project_path, 'Results', result_path)
        else:
            result_path = os.path.join(self._project_path, 'Results')

        result_path = os.path.abspath(os.path.expanduser(result_path))

        if result_name is not None:
            result_name = os.path.join(result_path, result_name)
        else:
            result_name = os.path.join(result_path, '<D>')

        try:
            with self._run_lock:
                self._run_data[name] = {
                    'status'            : '',
                    'run_id'            : '',
                    'guid'              : None,
                    'params'            : sequence_list,
                    'rtype'             : 'SequenceRun',
                    'total_injections'  : len(sequence_list),
                    'current_injection' : None,
                    'acq_method'        : acq_method_list,
                    }

            result = self.controller.SubmitSequenceRun(sequence, result_name)
            success = True

            with self._run_lock:
                self._run_ids[result.RunId.ToString()] = name
                self._run_data[name]['run_id'] = result.RunId.ToString()
                self._run_data[name]['guid'] = result.RunId

            logger.info('Submitted a %s item sequence to HPLC %s',
                len(sequence_list), self.name)

        except Exception:
            logger.error('Failed to submit sequence to HPLC {}:\n{}'.format(
                self.name, traceback.format_exc()))
            success = False

        if success:
            with self._run_lock:
                self._run_queue.append(name)
        else:
            with self._run_lock:
                if name in self._run_data:
                    del self._run_data[name]

        return success, sequence

    def abort_current_run(self):
        """
        Aborts the current running sample or sequence. Note that this
        aborts the entire sequence, not just the sample running in the
        sequence. Also, you can only abort currently running items, so
        if the item at the top of the queue is paused you will get an
        error rather than aborting it.
        """
        self.controller.AbortCurrentSingleOrSequenceRun()

    def pause_run_queue(self):
        """
        Pauses the run queue. Note that this will pause between items in
        a sequence.
        """

        self.controller.PauseRunQueue()

    def resume_run_queue(self):
        """
        Resumes the run queue
        """
        self.controller.ResumeRunQueue()

    def _inner_get_pump_property(self, pump_id):
        pump_id, valid = self._validate_pump_id(pump_id)

        if valid:
            self._get_pump_properties(pump_id)

        return pump_id, valid

    def _inner_get_autosampler_property(self, as_id):
        as_id, valid = self._validate_as_id(as_id)

        if valid:
            self._get_autosampler_properties(as_id)

        return as_id, valid

    def _inner_get_uv_property(self, uv_id):
        uv_id, valid = self._validate_uv_id(uv_id)

        if valid:
            self._get_uv_properties(uv_id)

        return uv_id, True

    def _validate_pump_id(self, pump_id):
        if not self._has_pump:
            logger.error('HPLC %s has no pump', self.name)
            return pump_id, False

        if pump_id is None:
            pump_id = self._pumps[0]

        if not pump_id in self._pumps:
            logger.error('HPLC %s has no pump with the Hashkey %s', self.name,
                pump_id)
            return pump_id, False

        return pump_id, True

    def _validate_as_id(self, as_id):
        if not self._has_autosampler:
            logger.error('HPLC %s has no autosampler', self.name)
            return as_id, False

        if as_id is None:
            as_id = self._autosamplers[0]

        if not as_id in self._autosamplers:
            logger.error('HPLC %s has no autosampler with the Hashkey %s',
                self.name, as_id)
            return as_id, False

        return as_id, True

    def _validate_uv_id(self, uv_id):
        if not self._has_uv:
            logger.error('HPLC %s has no detector', self.name)
            return uv_id, False

        if uv_id is None:
            uv_id = self._uvs[0]

        if not uv_id in self._uvs:
            logger.error('HPLC %s has no detector with the Hashkey %s',
                self.name, uv_id)
            return uv_id, False

        return uv_id, True

    def _run_from_callback(self):
        while True:
            if len(self._callback_queue) > 0:
                cmd, source, args = self._callback_queue.popleft()
                self._callback_cmds[cmd](source, args)

            else:
                time.sleep(0.01)

            if self._callback_stop.is_set():
                break

    def reconnect(self):
        """
        Run this method to reconnect if the instrument becomes disconnected after
        you've run the initial connect method.
        """
        # Connect to the controller
        self.controller.AppInitialized += self._on_connected_callback

        self.controller.EstablishConnection(self._device, self._user_ticket,
            '{}'.format(self._instrument_data[self._instrument_name]['id']),
            '{}'.format(self._project_data[self._project_name]['id']))

    def disconnect(self):
        """
        This method cleanly disconnects from the instrument.
        """
        for trace in self._traces.values():
            self.controller.UnsubscribePlotData(trace)

        self.controller.ModuleConfigurationChanged -= self._on_generic_callback
        self.controller.SampleContainerConfigChanged -= self._on_as_drawer_callback
        self.controller.RunQueueStatusChanged -= self._on_run_queue_status_callback
        self.controller.RunRecordChanged -= self._on_run_record_changed_callback
        self.controller.RunRecordCollectionChanged -= self._on_run_collection_callback
        self.controller.InstrumentTraceAddedEvent -= self._on_trace_added_callback
        self.controller.InstrumentPointsChangeEvent -= self._on_trace_data_callback
        self.controller.InstrumentTraceRemovedEvent += self._on_trace_removed_callback
        self.controller.InformClientCorrectXAxisEvent -= self._on_x_trace_change_callback
        self.controller.InformClientRunStartedEvent += self._on_run_start_callback
        self.controller.InstrumentStateInfoChangedEvent -= self._on_inst_state_changed_callback
        self.controller.DisconnectEvent -= self._on_disconnect_callback

        self._callback_stop.set()
        self._callback_thread.join()
        self.controller.Disconnect()
        self._connected = False


if __name__ == '__main__':
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    h1 = logging.StreamHandler(sys.stdout)
    h1.setLevel(logging.DEBUG)
    h1.setLevel(logging.INFO)
    # h1.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s')
    h1.setFormatter(formatter)
    logger.addHandler(h1)

    name = 'HPLC'
    device = 'net.pipe://localhost/Agilent/OpenLAB/'
    instrument_name = 'Agilent_HPLC'
    project_name = 'HPLC'

    # name = 'SEC-SAXS'
    # device = 'net.pipe://localhost/Agilent/OpenLAB/'
    # instrument_name = 'SEC-SAXS'
    # project_name = 'Demo'

    my_hplc = AgilentHPLC(name, device, instrument_name, project_name)

    print('waiting to connect')
    while not my_hplc.get_connected():
        time.sleep(0.1)

    time.sleep(1)

    # single_sample = {
    #     'acq_method'    : 'SEC-MALS',
    #     'sample_loc'    : 'D2F-A3',
    #     'injection_vol' : 10.0,
    #     'sample_name'   : 'test',
    #     'sample_descrip': 'test',
    #     'sample_type'   : 'Sample',
    #     }

    # result_path = 'api_test'
    # result_name = '<D>-api_test'

    # my_hplc.submit_single_sample('test', single_sample, result_path, result_name)
    # time.sleep(1)
    # my_hplc.submit_single_sample('test1', single_sample, result_path, result_name)
    # time.sleep(1)
    # my_hplc.submit_single_sample('test2', single_sample, result_path, result_name)
    # time.sleep(1)
    # my_hplc.submit_single_sample('test3', single_sample, result_path, result_name)
    # time.sleep(1)

    # my_hplc.remove_runs_from_queue(['test1'])

    # time.sleep(30)
    # my_hplc.abort_current_run()

    # #SEC-MALS
    # seq_sample1 = {
    #     'acq_method'    : 'SEC-MALS',
    #     'sample_loc'    : 'D2F-A1',
    #     'injection_vol' : 10.0,
    #     'sample_name'   : 'test1',
    #     'sample_descrip': 'test',
    #     'sample_type'   : 'Sample',
    #     }

    # seq_sample2 = {
    #     'acq_method'    : 'SEC-MALS',
    #     'sample_loc'    : 'D2F-A2',
    #     'injection_vol' : 10.0,
    #     'sample_name'   : 'test2',
    #     'sample_descrip': 'test',
    #     'sample_type'   : 'Sample',
    #     }

    # #SEC-SAXS
    # seq_sample1 = {
    #     'acq_method'    : 'SECSAXS_test',
    #     'sample_loc'    : 'D2F-A1',
    #     'injection_vol' : 10.0,
    #     'sample_name'   : 'test1',
    #     'sample_descrip': 'test',
    #     'sample_type'   : 'Sample',
    #     }

    # seq_sample2 = {
    #     'acq_method'    : 'SECSAXS_test',
    #     'sample_loc'    : 'D2F-A1',
    #     'injection_vol' : 10.0,
    #     'sample_name'   : 'test2',
    #     'sample_descrip': 'test',
    #     'sample_type'   : 'Sample',
    #     }

    # sample_list = [seq_sample1, seq_sample2]
    # result_path = 'api_test'
    # result_name = '<D>-api_test_seq'

    # my_hplc.submit_sequence('test_seq', sample_list, result_path, result_name)

    # time.sleep(30)
    # my_hplc.abort_current_run()

    # pump_mids = my_hplc.get_all_pump_method_ids()
    # pump_mvals = my_hplc.get_pump_method_values(pump_mids)
    # my_hplc.set_pump_method_values({'Flow': 0.0})
    # my_hplc.send_current_method_to_instrument()


    # #Example of setting a sample method propety, which is a bit tricky
    # my_hplc.load_sample_prep_method('test_prep')
    # val_list = List[ResourceIdAndValue]()

    # val = ResourceIdAndValue()
    # val.PropertyId = 'Draw'

    # sub_val_list = List[ResourceIdAndValue]()

    # sv1 = ResourceIdAndValue()
    # sv1.PropertyId = 'Source'
    # sv1.PropertyValue = 'ActualPosition'

    # sv2 = ResourceIdAndValue()
    # sv2.PropertyId = 'Volume_Mode'
    # sv2.PropertyValue = 'Default'
    # # sv2.PropertyId = 'Volume_Value'
    # # sv2.PropertyValue = '10.0'

    # sv3 = ResourceIdAndValue()
    # sv3.PropertyId = 'Speed_Mode'
    # sv3.PropertyValue = 'Default'

    # sv4 = ResourceIdAndValue()
    # sv4.PropertyId = 'Offset_Mode'
    # sv4.PropertyValue = 'Default'

    # sub_val_list.Add(sv1)
    # sub_val_list.Add(sv2)
    # sub_val_list.Add(sv3)
    # sub_val_list.Add(sv4)

    # sub_val_array = sub_val_list.ToArray()

    # val.PropertyValue = sub_val_array

    # val_list.Add(val)

    # val_array = val_list.ToArray()

    # settings = {'InstructionTable': val_array}

    # my_hplc.set_sample_prep_method_values(settings)
    # my_hplc.save_current_sample_prep_method()


    # my_hplc.disconnect()