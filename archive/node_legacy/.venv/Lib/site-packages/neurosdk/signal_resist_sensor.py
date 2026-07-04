import contextlib
from abc import abstractmethod, ABC

from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor


class SignalResistSensor(Sensor, ABC):
    def __init__(self, ptr):
        super().__init__(ptr)
        self.signalResistDataReceived = None
        self.set_signal_resist_callbacks()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.signalResistDataReceived = None
                self.unset_signal_resist_callbacks()
        super().__del__()

    @abstractmethod
    def set_signal_resist_callbacks(self):
        pass

    @abstractmethod
    def unset_signal_resist_callbacks(self):
        pass
