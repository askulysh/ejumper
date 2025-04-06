# bluetoothctl
# scan on
# trust XX:XX:XX:XX:XX:XX
# pair XX:XX:XX:XX:XX:XX

import gatt
import json
import sys
import minimalmodbus
import json
from datetime import datetime

manager = gatt.DeviceManager(adapter_name='hci0')
bms = {}

class AnyDevice(gatt.Device):
    def connect_succeeded(self):
        super().connect_succeeded()
        #print("[%s] Connected" % (self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        #print("[%s] Connection failed: %s" % (self.mac_address, str(error)))

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        #print("[%s] Disconnected" % (self.mac_address))
        self.manager.stop()

    def services_resolved(self):
        super().services_resolved()

        device_information_service = next(
            s for s in self.services
            if s.uuid == '0000ff00-0000-1000-8000-00805f9b34fb')

        self.bms_read_characteristic = next(
            c for c in device_information_service.characteristics
            if c.uuid == '0000ff01-0000-1000-8000-00805f9b34fb')

        self.bms_write_characteristic = next(
            c for c in device_information_service.characteristics
            if c.uuid == '0000ff02-0000-1000-8000-00805f9b34fb')

        #print("BMS found")
        self.bms_read_characteristic.enable_notifications()

    def characteristic_enable_notifications_succeeded(self, characteristic):
        super().characteristic_enable_notifications_succeeded(characteristic)
        print("BMS request generic data")
        self.response=bytearray()
        self.rawdat={}
        self.get_voltages=False
        self.get_hw_version=False
        self.bms_write_characteristic.write_value(
            bytes([0xDD,0xA5,0x03,0x00,0xFF,0xFD,0x77]));

    def characteristic_enable_notifications_failed(self, characteristic, error):
        super.characteristic_enable_notifications_failed(characteristic, error)
        print("BMS notification failed:",error)

    def characteristic_value_updated(self, characteristic, value):
        #print("BMS answering")
        self.response+=value
        if self.response.endswith(b'w') :
            #print("BMS answer:", self.response.hex())
            self.response=self.response[4:]
            if self.get_hw_version :
                self.rawdat['hw']=self.response[0:26].decode('utf-8')
                #print(json.dumps(self.rawdat, indent=1, sort_keys=True))
                self.disconnect();
            elif self.get_voltages :
                packVolts=0
                for i in range(int(len(self.response)/2)-1):
                    cell=int.from_bytes(self.response[i*2:i*2+2], byteorder = 'big')/1000
                    self.rawdat['V{0:0=2}'.format(i+1)]=cell
                    packVolts += cell
                # + self.rawdat['V{0:0=2}'.format(i)]
                self.rawdat['Vbat'] = round(packVolts, 3)
                #print("BMS chat ended")

                global bms
                bms = dict(self.rawdat)
                #print(json.dumps(self.rawdat, indent=1, sort_keys=True))
                self.disconnect();
            else:
                self.rawdat['Ibat']=int.from_bytes(
                    self.response[2:4], byteorder = 'big',signed=True)/100.0
                self.rawdat['CapBalance']=int.from_bytes(
                    self.response[4:6], byteorder = 'big',signed=True)/100.0
                self.rawdat['CapRate']=int.from_bytes(
                    self.response[6:8], byteorder = 'big',signed=True)/100.0
                self.rawdat['Cycle']=int.from_bytes(
                    self.response[8:10], byteorder = 'big',signed=True)
                date = int.from_bytes(self.response[10:12],byteorder = 'big',
                                    signed=True)

                self.rawdat['ProdDate']=str(date&0x1f)+' '+ str((date>>5)&0x0f)+' '+str((date>>9)+2000)
                self.rawdat['Bal']=int.from_bytes(
                    self.response[12:14], byteorder = 'big',signed=False)
                self.rawdat['Prot']=int.from_bytes(
                    self.response[16:18],byteorder = 'big',signed=False)
                self.rawdat['SoftVer']=self.response[18]
                self.rawdat['Percent']=self.response[19]
                self.rawdat['FET']=self.response[20]
                self.rawdat['NBat']=self.response[21]
                for i in range(self.response[22]): # read temperatures
                    self.rawdat['T{0:0=1}'.format(i+1)]=(int.from_bytes(
                        self.response[23+i*2:i*2+25],'big')-2731)/10

                self.response=bytearray()
                print("BMS request voltages")
                self.get_voltages=True
                self.bms_write_characteristic.write_value(
                    bytes([0xDD,0xA5,0x04,0x00,0xFF,0xFC,0x77]));
#                self.get_hw_version=True
#                self.bms_write_characteristic.write_value(bytes(
#                    [0xDD,0xA5,0x05,0x00,0xFF,0xFB,0x77]));

    def characteristic_write_value_failed(self, characteristic, error):
        print("BMS write failed:",error)

def battery_bms_read(mac) :
    device = AnyDevice(mac_address=mac, manager=manager)
    device.connect()
    manager.run()

def renology_read(modbus_device="/dev/ttyUSB0", modbus_slave_address=1):
    instrument = minimalmodbus.Instrument(modbus_device, modbus_slave_address)
    # port name, slave address (in decimal)
    instrument.serial.baudrate = 9600
    instrument.serial.bytesize = 8
    instrument.serial.parity = minimalmodbus.serial.PARITY_NONE
    instrument.serial.stopbits = 2
    instrument.serial.timeout  = 1
    instrument.address = modbus_slave_address # this is the slave address number
    instrument.mode = minimalmodbus.MODE_RTU   # rtu or ascii mode
    instrument.clear_buffers_before_each_transaction = True

    # # Temperature
    # # The actual value has to be split, the highest bit of each is the +/- sign
    temp = instrument.read_register(0x103)
    if (temp & 0x8000) > 0 :
        # This is the positive/negative bit for the Controller Temperature
        tempControllerSign = "-"
    else :
        tempControllerSign = ""
    if (temp & 0x80) > 0 :
        # This is the positive/negative bit for the Aux Battery Temperature
        tempAuxBattSign = "-"
    else :
        tempAuxBattSign = ""
    # Strips the high byte to show Controller Temperature
    tempController = "{}{}".format(tempControllerSign,
                                   int(format(temp & 0x7F00, '016b')[:8], 2))
    # Low byte shows Aux Battery Temperature
    tempAuxBatt = "{}{}".format(tempAuxBattSign, (temp & 0x7F))

    # # Charge State
    # # If the bit is "1" then the value is True, comment is from the Renogy Docs
    chargeState = instrument.read_register(0x120)
    # 00H:no charging activated
    chargingNone = (chargeState & 0x1) > 0
    # 02H:mppt charging mode  (solar)
    chargingSolar = (chargeState & 0x4) > 0
    # 03H:Equallization charging stage  (solar/alternator)
    chargingEqualization = (chargeState & 0x8) > 0
    # 04H:Boost charging stage  (solar/alternator)
    chargingBoost = (chargeState & 0x10) > 0
    # 05H:Float charging stage  (solar/alternator)
    chargingFloat = (chargeState & 0x20) > 0
    # 06H:current-limited charging stage (solar/alternator)
    chargingLimited = (chargeState & 0x40) > 0
    # 08H:direct charging mode (alternator)
    chargingAlt = (chargeState & 0x80) > 0

    # Error Codes
	# If the bit is "1" then the string is added to the array,
    # comment is from the Renogy Docs
    errors = []
    errorCodesLow = instrument.read_register(0x121)
    if (errorCodesLow & 0x10) > 0 :
        # b4:controller inside over temperature 2
        errors.append("CtrlOverTemp2")

    if (errorCodesLow & 0x20) > 0 :
        # b5:alternator input overcurrent
        errors.append("AltInputOverCurrent")

    if (errorCodesLow & 0x100) > 0 :
        # b8：alternator input over voltage protection
        errors.append("AltInputOverVoltProtection")

    if (errorCodesLow & 0x200) > 0 :
        # b9：starter battery reverse polarity
        errors.append("StarterBatteryReversePolarity")
    if (errorCodesLow & 0x400) > 0 :
        # b10：BMS over charge protection
        errors.append("BmsOverChargeProtection")
    if (errorCodesLow & 0x800) > 0 :
        # b11：auxilliary battery stopped taking charges because of
        # low temperature (lithium battery:0°C, lead acid:-35°C)
        errors.append("AuxLowTempProtection")

    errorCodesHigh = instrument.read_register(0x122)
    if (errorCodesHigh & 0x1) > 0 :
        # B0:auxilliary battery over-discharged
        errors.append("AuxBatteryOverDischarge")
    if (errorCodesHigh & 0x2) > 0 :
        # b1:auxilliary battery over voltage
        errors.append("AuxBatteryOverVolt")
    if (errorCodesHigh & 0x4) > 0 :
        # B2:auxilliary battery under voltage warning
        errors.append("AuxBatteryUnderVolt")
    if (errorCodesHigh & 0x20) > 0 :
        # B5:controller inside temperature too high
        errors.append("ControllerOverTemp")
    if (errorCodesHigh & 0x40) > 0 :
        # B6:auxilliary battery over temperature
        errors.append("AuxBatteryOverTemp")
    if (errorCodesHigh & 0x80) > 0 :
        # B7:solar input too high
        errors.append("SolarInputTooHigh")
    if (errorCodesHigh & 0x200) > 0 :
        # B9:solar input over voltage
        errors.append("SolarInputOverVolt")
    if (errorCodesHigh & 0x1000) > 0 :
        # B12:solar, reversed poliarity
        errors.append("SolarReversePolarity")

    renology = {
        "device": instrument.read_string(0xc,8),
        # Auxilliary battery State of charge
        "auxSoc": instrument.read_register(0x100),
        "auxVoltage": instrument.read_register(0x101,1),
        # combined charging current from solar+alternator to the auxilliary battery
        "maxCharge": instrument.read_register(0x102,2),
        "controllerTemp": int(tempController),
        "auxTemp": int(tempAuxBatt),
        "altVoltage": instrument.read_register(0x104,1),
        "altAmps": instrument.read_register(0x105,2),
        "altWatts": instrument.read_register(0x106),
        "solVoltage": instrument.read_register(0x107,1),
        "solAmps": instrument.read_register(0x108,2),
        "solWatts": instrument.read_register(0x109),
        # values returned need to be divided by 10 to transpose to Volts
        "lowDailyVolts": instrument.read_register(0x10b)/10,
        # values returned need to be divided by 10 to transpose to Volts
        "highDailyVolts": instrument.read_register(0x10c)/10,
        # solar+alternator
        "highDailyCurrent": instrument.read_register(0x10d),
        # solar+alternator
        "highDailyPower": instrument.read_register(0x10f),
        # solar+alternator
        "highAccumAh": instrument.read_register(0x111),
        # solar+alternator
        "dailyGeneratedPower": instrument.read_register(0x113),
        "totalWorkingDays": instrument.read_register(0x115),
        "totalOverdischargedBattery": instrument.read_register(0x116),
        "totalChargedBattery": instrument.read_register(0x117),
        "timestamp": str(datetime.now()),
        "chargingNone": str(chargingNone),
        "chargingSolar": str(chargingSolar),
        "chargingEqualization": str(chargingEqualization),
        "chargingBoost": str(chargingBoost),
        "chargingFloat": str(chargingFloat),
        "chargingLimited": str(chargingLimited),
        "chargingAlt": str(chargingAlt),
        "errors": errors
        }
    return renology
    payload = json.dumps(renology, indent=1, sort_keys=True)
    #print(payload)
    #print(renology)

    try:
        return payload
    except Exception as e:
        return e

if (len(sys.argv)<2):
    print("Usage: einfo.py <device_uuid>")
else:
    battery_bms_read(sys.argv[1])
    renology = renology_read()
    print(renology)
    print("Solar:")
    print("  V:", renology['solVoltage'], "I:", renology['solAmps'],
          "W:", renology['solWatts'],
          round(float(renology['solVoltage'])*float(renology['solAmps']),3))
    print("Battery:")
    print("  V:", renology['auxVoltage'], bms['Vbat'], "I:", bms['Ibat'],
          "W:", bms['Vbat']*bms['Ibat'], bms['Percent'], '%')
