import contextlib
from abc import abstractmethod, ABC

from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor, _neuro_lib


class EnvelopeSensor(Sensor, ABC):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readSamplingFrequencyEnvelopeSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readSamplingFrequencyEnvelopeSensor.restype = c_uint8
        if self.is_supported_feature(SensorFeature.Envelope):
            self.envelopeDataReceived = None
            self.set_envelope_callbacks()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.envelopeDataReceived = None
                self.unset_envelope_callbacks()
        super().__del__()

    @property
    def sampling_frequency_envelope(self) -> SensorSamplingFrequency:
        status = OpStatus()
        sf_val = EnumType(c_int8(1))
        _neuro_lib.readSamplingFrequencyEnvelopeSensor(self.sensor_ptr, sf_val, byref(status))
        raise_exception_if(status)
        return SensorSamplingFrequency(sf_val.contents.value)

    @abstractmethod
    def set_envelope_callbacks(self):
        pass

    @abstractmethod
    def unset_envelope_callbacks(self):
        pass
