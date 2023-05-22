print(f"Loading {__file__}...")

from collections import OrderedDict
from ophyd.signal import (EpicsSignal, EpicsSignalRO)
from ophyd.device import Device
from ophyd.device import (Component as C, DynamicDeviceComponent as DDC)

class Channel(Device):
    '''Bimorph Channel'''
    user_setpoint = C(EpicsSignal, '_SP.VAL')
    target_voltage = C(EpicsSignalRO, '_TARGET_MON.VAL')
    current_voltage = C(EpicsSignalRO, '_CURRENT_MON.VAL')
    min_voltage = C(EpicsSignalRO, '_MINV_MON.VAL')
    max_voltage = C(EpicsSignalRO, '_MINV_MON.VAL')


def add_channels(range_, **kwargs):
    '''Add one or more Channel to an Bimorph instance
       Parameters:
       -----------
       range_ : sequence of ints
           Must be be in the set [0,31]
       By default, an Bimorph is initialized with all 32 channels.
       These provide the following Components as EpicsSignals (N=[0,31]):
       Bimorph.channels.channelN.(fields...)
       '''
    defn = OrderedDict()

    for ch in range_:
        if not (0 <= ch < 32):
            raise ValueError('Channel must be in the set [0,31]')

        attr = 'channel{}'.format(ch+1)
        defn[attr] = (Channel, ':U{}'.format(ch), kwargs)

    return defn

class Bimorph(Device):
    '''Bimorph HV Power Source'''

    bank_no = C(EpicsSignal, ':BANK_NO_32.VAL')
    step_size = C(EpicsSignal, ':U_STEP.VAL')
    inc_bank = C(EpicsSignal, ':INCR_U_BANK_CMD.PROC')
    dec_bank = C(EpicsSignal, ':DECR_U_BANK_CMD.PROC')
    stop_ramp = C(EpicsSignal, ':STOP_RAMPS_BANK.PROC')
    start_ramp = C(EpicsSignal, ':START_RAMPS_CMD.PROC')

    format_number = C(EpicsSignal, ':FORMAT_NO_SP.VAL')
    load_format = C(EpicsSignal, ':FORMAT_ACTIVE_SP.PROC')

    all_target_voltages = C(EpicsSignalRO, ':U_ALL_TARGET_MON.VAL')
    all_current_voltages = C(EpicsSignalRO, ':U_ALL_CURRENT_MON.VAL')

    unit_status = C(EpicsSignalRO, ':UNIT_STATUS_MON.A')

    channels = DDC(add_channels(range(0, 32)))

    def step(self, bank, size, direction, start=False, wait=False):
        self.bank_no.put(bank)
        self.step_size.put(size)

        if(direction == "inc"):
            self.inc_bank.put(1)
        else:
            self.dec_bank.put(1)

        if(start):
            self.start()

        if(wait):
            self.wait()

    def increment_bank(self, bank, size, start=False, wait=False):
        ''' Increments the target voltage in `size` Volts in the specified `bank`

        Parameters:
        -----------
        bank : int
            The number of the bank to be incremented
        size : float
            The amount of Volts to increment from the bank target value
        start : bool
            Determines if the ramp must start right after the increment. Defaults to False.
        wait : bool
            Determines if the code must wait until the ramp process finishes. Defaults to False.
        '''
        self.step(bank, size, "inc", start)

    def decrement_bank(self, bank, size, start=False, wait=False):
        ''' Decrements the target voltage in `size` Volts in the specified `bank`

        Parameters:
        -----------
        bank : int
            The number of the bank to be decremented
        size : float
            The amount of Volts to decrement from the bank target value
        start : bool
            Determines if the ramp must start right after the decrement. Defaults to False.
        wait : bool
            Determines if the code must wait until the ramp process finishes. Defaults to False.
        '''
        self.step(bank, size, "dec", start)

    def start(self):
        ''' Start the Ramping process on all channels '''
        self.start_ramp.put(1)

    def stop(self):
        ''' Stops the Ramping process on all channels '''
        self.stop_ramp.put(1)

    def is_ramping(self):
        ''' Returns wether the power supply is ramping or not '''
        return (int(self.unit_status.get()) >> 30) == 1

    def is_interlock_ok(self):
        ''' Returns the interlock state '''
        st = int(self.unit_status.get())
        return (st & 1) & ((st >> 1) & 1) == 1

    def is_on(self):
        ''' Returns wether the Channels are ON or OFF '''
        return (int(self.unit_status.get()) >> 29) == 1          

    def wait(self):
        while self.is_ramping():
          sleep(0.1)

bimorph = Bimorph('XF:16IDA-OP{Mir:KB-PS}', name='bimorph')



