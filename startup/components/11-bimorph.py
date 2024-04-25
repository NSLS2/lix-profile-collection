print(f"Loading {__file__}...")

from collections import OrderedDict
from ophyd.signal import (Signal, EpicsSignal, EpicsSignalRO)
from ophyd import Device, PVPositioner, PVPositionerPC
from ophyd import (Component as C, DynamicDeviceComponent as DDC)

class Channel(PVPositionerPC):
    '''Bimorph Channel'''
    setpoint = C(EpicsSignal, '_SP.VAL')
    readback = C(EpicsSignalRO, '_CURRENT_MON_VAL.VAL')
    armed_voltage = C(EpicsSignalRO, '_SP_MON.VAL')
    #target_voltage = C(EpicsSignalRO, '_TARGET_MON_VAL.VAL')
    #min_voltage = C(EpicsSignalRO, '_MINV_MON.VAL')
    #max_voltage = C(EpicsSignalRO, '_MAXV_MON.VAL')

    # done = Cpt(Signal, value=0)

    # done_value = 0

    # def read(self):

    #     res = super().read()
    #     for key in res.keys():
    #         value = res[key]["value"]
    #         value = np.atleast_1d(value)
    #         if len(value) > 0:
    #             value = value[0]
    #         res[key]["value"] = value

    #     return res

    # def describe(self):

    #     res = super().describe()

    #     for key in res.keys():

    #         res[key]["shape"] = []
    #         res[key]["dtype"] = "integer" if "done" in key else "number"

    #     return res


    #done = Cpt(EpicsSignalRO, 'Cmd-Busy')
    #stop_signal = Cpt(EpicsSignal, 'Cmd-Cmd')


    # def set(self, value):

    #     # if (value < self.min_voltage.get()):
    #     #     raise ValueError("Desired voltage is too low!")
    #     # if (value > self.max_voltage.get()):
    #     #     raise ValueError("Desired voltage is too high!")



    #     return st

    # def get(self):

    #     return self.setpoint.get()


def add_channels(range_, **kwargs):
    '''Add one or more Channel to an Bimorph instance
       Parameters:
       -----------
       range_ : sequence of ints
           Must be be in the set [0,31]
       By default, an Bimorph is initialized with all 32 channels.
       These provide the following Cs as EpicsSignals (N=[0,31]):
       Bimorph.channels.channelN.(fields...)
       '''
    defn = OrderedDict()

    for ch in range_:
        if not (0 <= ch < 32):
            raise ValueError('Channel must be in the set [0,31]')

        attr = 'channel{}'.format(ch)
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

    def start_plan(self):
        yield from bps.mv(self.start_ramp, 1)

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

    def all_armed_voltages(self):
        return np.array([getattr(self, f"channels.channel{i}.armed_voltage").get() for i in range(32)], dtype=np.float32).ravel()

    def all_setpoint_voltages(self):
        return np.array([getattr(self, f"channels.channel{i}.setpoint").get() for i in range(32)], dtype=np.float32).ravel()

bimorph = Bimorph('XF:16IDA-OP{Mir:KB-PS}', name='bimorph')


for i in range(24):

    channel = getattr(bimorph, f"channels.channel{i}")
    channel.set(0)

time.sleep(2e0)

bimorph.start()


class PseudoBimorph(PseudoPositioner):
    """
    Interface to three positioners in a coordinate system that flips the sign.
    """
    p0 = C(PseudoSingle)
    p1 = C(PseudoSingle)
    p2 = C(PseudoSingle)
    p3 = C(PseudoSingle)
    p4 = C(PseudoSingle)
    p5 = C(PseudoSingle)
    p6 = C(PseudoSingle)
    p7 = C(PseudoSingle)
    p8 = C(PseudoSingle)
    p9 = C(PseudoSingle)
    p10 = C(PseudoSingle)
    p11 = C(PseudoSingle)

    r0 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U12")
    r1 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U13")
    r2 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U14")
    r3 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U15")
    r4 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U16")
    r5 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U17")
    r6 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U18")
    r7 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U19")
    r8 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U20")
    r9 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U21")
    r10 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U22")
    r11 = C(Channel, "XF:16IDA-OP{Mir:KB-PS}:U23")

    dim = 12

    @property
    def transform(self):

        # transform with Legendre polynomials
        T = np.zeros((self.dim, self.dim))
        x = np.linspace(-1, 1, self.dim)
        for i in range(self.dim):
            T[:, i] = sp.special.legendre(i, monic=False)(x)

        # difference between neighbors
        #T = np.tril(np.ones((self.dim, self.dim)))

        return T

    @property
    def inverse_transform(self):
        return sp.linalg.inv(self.transform)
    
    @pseudo_position_argument
    def forward(self, pseudo_pos):
        "Given a position in the psuedo coordinate system, transform to the real coordinate system."
        pseudo_vector = [getattr(pseudo_pos, f'p{i}') for i in range(self.dim)]
        real_pos_kwargs = {f'r{i}':pos for i, pos in enumerate(self.transform @ pseudo_vector)}
        return self.RealPosition(**real_pos_kwargs)

    @real_position_argument
    def inverse(self, real_pos):
        real_vector = [getattr(real_pos, f'r{i}') for i in range(self.dim)]
        pseudo_pos_kwargs = {f'p{i}':pos for i, pos in enumerate(self.inverse_transform @ real_vector)}
        "Given a position in the real coordinate system, transform to the pseudo coordinate system."
        return self.PseudoPosition(**pseudo_pos_kwargs)

pseudo_bimorph = PseudoBimorph(name='pseudo_bimorph')

for i in range(12):

    p = getattr(pseudo_bimorph, f'p{i}')
    r = getattr(pseudo_bimorph, f'r{i}')

    p.readback.name = p.name
    r.readback.name = r.name