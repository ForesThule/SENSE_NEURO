import contextlib
from ctypes import c_int8, byref, py_object, POINTER, c_uint8
from neurosdk.__cmn_types import EnumType, OpStatus, FPGDataCallbackNeuroSmart, FPGDataListenerHandle
from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.cmn_types import *
from neurosdk.sensor import Sensor, _neuro_lib


class FpgSensor(Sensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.readSamplingFrequencyFPGSensor.argtypes = [SensorPointer, POINTER(c_int8), POINTER(OpStatus)]
        _neuro_lib.readSamplingFrequencyFPGSensor.restype = c_uint8
        _neuro_lib.readIrAmplitudeFPGSensor.argtypes = [SensorPointer, POINTER(c_uint8), POINTER(OpStatus)]
        _neuro_lib.readIrAmplitudeFPGSensor.restype = c_uint8
        _neuro_lib.writeIrAmplitudeFPGSensor.argtypes = [SensorPointer, c_int8, POINTER(OpStatus)]
        _neuro_lib.writeIrAmplitudeFPGSensor.restype = c_uint8
        _neuro_lib.readRedAmplitudeFPGSensor.argtypes = [SensorPointer, POINTER(c_uint8), POINTER(OpStatus)]
        _neuro_lib.readRedAmplitudeFPGSensor.restype = c_uint8
        _neuro_lib.writeRedAmplitudeFPGSensor.argtypes = [SensorPointer, c_uint8, POINTER(OpStatus)]
        _neuro_lib.writeRedAmplitudeFPGSensor.restype = c_uint8
        _neuro_lib.addFPGDataCallback.argtypes = [SensorPointer, FPGDataCallbackNeuroSmart, c_void_p,
                                                            ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addFPGDataCallback.restype = c_uint8
        _neuro_lib.removeFPGDataCallback.argtypes = [FPGDataListenerHandle]
        _neuro_lib.removeFPGDataCallback.restype = c_void_p
        if self.is_supported_feature(SensorFeature.FPG):
            self.fpgDataReceived = None
            self.__add_fpg_data_callback_neuro_smart()
        self.__closed = False

    def __del__(self):
        with contextlib.suppress(Exception):
            if not self.__closed:
                self.__closed = True
                self.fpgDataReceived = None
                _neuro_lib.removeFPGDataCallback(self.__fpgDataCallbackNeuroSmartHandle)
        super().__del__()

    @property
    def sampling_frequency_fpg(self) -> SensorSamplingFrequency:
        status = OpStatus()
        sampling_frequency_out = EnumType(c_int8(1))
        _neuro_lib.readSamplingFrequencyFPGSensor(self.sensor_ptr, sampling_frequency_out,
                                                                     byref(status))
        raise_exception_if(status)
        return SensorSamplingFrequency(sampling_frequency_out.contents.value)

    @property
    def ir_amplitude(self) -> IrAmplitude:
        status = OpStatus()
        enum_type = POINTER(c_uint8)
        amplitude_out = enum_type(c_uint8(1))
        _neuro_lib.readIrAmplitudeFPGSensor(self.sensor_ptr, amplitude_out, byref(status))
        raise_exception_if(status)
        return IrAmplitude(amplitude_out.contents.value)

    @ir_amplitude.setter
    def ir_amplitude(self, amplitude: IrAmplitude):
        status = OpStatus()
        _neuro_lib.writeIrAmplitudeFPGSensor(self.sensor_ptr, amplitude.value, byref(status))
        raise_exception_if(status)

    @property
    def red_amplitude(self) -> RedAmplitude:
        status = OpStatus()
        enum_type = POINTER(c_uint8)
        amplitude_out = enum_type(c_uint8(1))
        _neuro_lib.readRedAmplitudeFPGSensor(self.sensor_ptr, amplitude_out, byref(status))
        raise_exception_if(status)
        return RedAmplitude(amplitude_out.contents.value)

    @red_amplitude.setter
    def red_amplitude(self, amplitude: RedAmplitude):
        status = OpStatus()
        _neuro_lib.writeRedAmplitudeFPGSensor(self.sensor_ptr, amplitude.value, byref(status))
        raise_exception_if(status)

    def __add_fpg_data_callback_neuro_smart(self):
        def __py_fpg_data_callback_neuro_smart(ptr, data, sz_data, user_data):
            fpg_data = [FPGData(PackNum=int(data[i].PackNum),
                                IrAmplitude=float(data[i].IrAmplitude),
                                RedAmplitude=float(data[i].RedAmplitude))
                        for i in range(sz_data)]

            if user_data.fpgDataReceived is not None:
                user_data.fpgDataReceived(user_data, fpg_data)

        status = OpStatus()
        self.__fpgDataCallbackNeuroSmart = FPGDataCallbackNeuroSmart(__py_fpg_data_callback_neuro_smart)
        self.__fpgDataCallbackNeuroSmartHandle = FPGDataListenerHandle()
        _neuro_lib.addFPGDataCallback(self.sensor_ptr, self.__fpgDataCallbackNeuroSmart,
                                                byref(self.__fpgDataCallbackNeuroSmartHandle),
                                                py_object(self), byref(status))
        raise_exception_if(status)
