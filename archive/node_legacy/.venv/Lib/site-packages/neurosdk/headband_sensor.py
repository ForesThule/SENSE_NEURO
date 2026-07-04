from neurosdk.__utils import raise_exception_if
from neurosdk.__cmn_types import *
from neurosdk.amp_sensor import AmpSensor
from neurosdk.cmn_types import *
from neurosdk.fpg_sensor import FpgSensor
from neurosdk.mems_sensor import MemsSensor
from neurosdk.neuro_smart_sensor import NeuroSmartSensor
from neurosdk.resist_sensor import ResistSensor
from neurosdk.sensor import _neuro_lib
from neurosdk.signal_sensor import SignalSensor


class HeadbandSensor(AmpSensor, SignalSensor, ResistSensor, FpgSensor, NeuroSmartSensor, MemsSensor):
    def __init__(self, ptr):
        super().__init__(ptr)
        # signatures
        _neuro_lib.addResistCallbackHeadband.argtypes = [SensorPointer, ResistCallbackHeadband, c_void_p,
                                                         ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addResistCallbackHeadband.restype = c_uint8
        _neuro_lib.removeResistCallbackHeadband.argtypes = [HeadbandResistDataListenerHandle]
        _neuro_lib.removeResistCallbackHeadband.restype = c_void_p
        _neuro_lib.addSignalDataCallbackHeadband.argtypes = [SensorPointer, SignalDataCallbackHeadband, c_void_p,
                                                             ctypes.py_object, POINTER(OpStatus)]
        _neuro_lib.addSignalDataCallbackHeadband.restype = c_uint8
        _neuro_lib.removeSignalDataCallbackHeadband.argtypes = [HeadbandSignalDataListenerHandle]
        _neuro_lib.removeSignalDataCallbackHeadband.restype = c_void_p

    def __del__(self):
        super().__del__()

    def set_signal_callbacks(self):
        self.__add_signal_data_callback_headband()

    def unset_signal_callbacks(self):
        _neuro_lib.removeSignalDataCallbackHeadband(self.__signalDataCallbackHeadbandHandle)

    def set_resist_callbacks(self):
        self.__add_resist_callback_headband()

    def unset_resist_callbacks(self):
        _neuro_lib.removeResistCallbackHeadband(self.__resistCallbackHeadbandHandle)

    def __add_resist_callback_headband(self):
        def __py_resist_callback_headband(ptr, data, user_data):
            resist = HeadbandResistData(PackNum=int(data.PackNum),
                                        O1=float(data.O1),
                                        O2=float(data.O2),
                                        T3=float(data.T3),
                                        T4=float(data.T4))
            if user_data.resistDataReceived is not None:
                user_data.resistDataReceived(user_data, resist)

        status = OpStatus()
        self.__resistCallbackHeadband = ResistCallbackHeadband(__py_resist_callback_headband)
        self.__resistCallbackHeadbandHandle = HeadbandResistDataListenerHandle()
        _neuro_lib.addResistCallbackHeadband(self.sensor_ptr, self.__resistCallbackHeadband,
                                             byref(self.__resistCallbackHeadbandHandle),
                                             py_object(self), byref(status))
        raise_exception_if(status)

    def __add_signal_data_callback_headband(self):
        def __py_signal_data_callback_headband(ptr, data, sz_data, user_data):
            signal_data = [HeadbandSignalData(PackNum=int(data[i].PackNum),
                                              Marker=int(data[i].Marker),
                                              O1=float(data[i].O1),
                                              O2=float(data[i].O2),
                                              T3=float(data[i].T3),
                                              T4=float(data[i].T4)) for i in range(sz_data)]
            if user_data.signalDataReceived is not None:
                user_data.signalDataReceived(user_data, signal_data)

        status = OpStatus()
        self.__signalDataCallbackHeadband = SignalDataCallbackHeadband(__py_signal_data_callback_headband)
        self.__signalDataCallbackHeadbandHandle = HeadbandSignalDataListenerHandle()
        _neuro_lib.addSignalDataCallbackHeadband(self.sensor_ptr, self.__signalDataCallbackHeadband,
                                                 byref(self.__signalDataCallbackHeadbandHandle),
                                                 py_object(self), byref(status))
        raise_exception_if(status)
