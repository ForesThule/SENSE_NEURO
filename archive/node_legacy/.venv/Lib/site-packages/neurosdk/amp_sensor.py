import contextlib

from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor, _neuro_lib


class AmpSensor(Sensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readAmpMode.argtypes = [SensorPointer, POINTER(c_uint8), POINTER(OpStatus)]
        _neuro_lib.readAmpMode.restype = c_uint8
        _neuro_lib.addAmpModeCallback.argtypes = [SensorPointer, AmpModeCallback, c_void_p, ctypes.py_object,
                                                  POINTER(OpStatus)]
        _neuro_lib.addAmpModeCallback.restype = c_uint8
        _neuro_lib.removeAmpModeCallback.argtypes = [AmpModeListenerHandle]
        _neuro_lib.removeAmpModeCallback.restype = c_void_p
        self.sensorAmpModeChanged = None
        self.__add_amp_mode_callback()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.sensorAmpModeChanged = None
                _neuro_lib.removeAmpModeCallback(self.__ampModeCallbackHandle)
        super().__del__()

    @property
    def amp_mode(self) -> SensorAmpMode:
        status = OpStatus()
        enum_type = POINTER(c_uint8)
        mode_out = enum_type(c_uint8(1))
        _neuro_lib.readAmpMode(self.sensor_ptr, mode_out, byref(status))
        raise_exception_if(status)
        return SensorAmpMode(mode_out.contents.value)

    def __add_amp_mode_callback(self):
        def __py_amp_mode_callback(ptr, mode, user_data):
            if user_data.sensorAmpModeChanged is not None:
                user_data.sensorAmpModeChanged(user_data, SensorAmpMode(mode))

        status = OpStatus()
        self.__ampModeCallback = AmpModeCallback(__py_amp_mode_callback)
        self.__ampModeCallbackHandle = AmpModeListenerHandle()
        _neuro_lib.addAmpModeCallback(self.sensor_ptr, self.__ampModeCallback,
                                      byref(self.__ampModeCallbackHandle),
                                      py_object(self), byref(status))
        raise_exception_if(status)
