#!/usr/bin/python3
#
# usb-parse - Reads CSV file with data extracted from oscilloscope
#             by the `ds1054z` tool and parses USB 2.0 protocol.
#
#   Copyright (C) 2024 Roman Penyaev <r.peniaev@gmail.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from dataclasses import dataclass, field
from optparse import OptionParser
import csv
import sys

def usb_period(is_full_speed):
    if is_full_speed:
        return 1 / 12e6
    return 1 / 1.5e6

crc5_tbl = [0x00, 0x0b, 0x16, 0x1d, 0x05, 0x0e, 0x13, 0x18, 0x0a, 0x01,
            0x1c, 0x17, 0x0f, 0x04, 0x19, 0x12, 0x14, 0x1f, 0x02, 0x09,
            0x11, 0x1a, 0x07, 0x0c, 0x1e, 0x15, 0x08, 0x03, 0x1b, 0x10,
            0x0d, 0x06]

def usb_crc5(data):
    data = data ^ 0x1f
    lsb = (data >> 1) & 0x1f
    msb = (data >> 6) & 0x1f

    crc = 0x14 if (data & 1) != 0 else 0x00
    crc = crc5_tbl[(lsb ^ crc)]
    crc = crc5_tbl[(msb ^ crc)]

    return crc ^ 0x1f


crc16_tbl = [0x0000, 0xc0c1, 0xc181, 0x0140, 0xc301, 0x03c0, 0x0280, 0xc241, 0xc601,
             0x06c0, 0x0780, 0xc741, 0x0500, 0xc5c1, 0xc481, 0x0440, 0xcc01, 0x0cc0,
             0x0d80, 0xcd41, 0x0f00, 0xcfc1, 0xce81, 0x0e40, 0x0a00, 0xcac1, 0xcb81,
             0x0b40, 0xc901, 0x09c0, 0x0880, 0xc841, 0xd801, 0x18c0, 0x1980, 0xd941,
             0x1b00, 0xdbc1, 0xda81, 0x1a40, 0x1e00, 0xdec1, 0xdf81, 0x1f40, 0xdd01,
             0x1dc0, 0x1c80, 0xdc41, 0x1400, 0xd4c1, 0xd581, 0x1540, 0xd701, 0x17c0,
             0x1680, 0xd641, 0xd201, 0x12c0, 0x1380, 0xd341, 0x1100, 0xd1c1, 0xd081,
             0x1040, 0xf001, 0x30c0, 0x3180, 0xf141, 0x3300, 0xf3c1, 0xf281, 0x3240,
             0x3600, 0xf6c1, 0xf781, 0x3740, 0xf501, 0x35c0, 0x3480, 0xf441, 0x3c00,
             0xfcc1, 0xfd81, 0x3d40, 0xff01, 0x3fc0, 0x3e80, 0xfe41, 0xfa01, 0x3ac0,
             0x3b80, 0xfb41, 0x3900, 0xf9c1, 0xf881, 0x3840, 0x2800, 0xe8c1, 0xe981,
             0x2940, 0xeb01, 0x2bc0, 0x2a80, 0xea41, 0xee01, 0x2ec0, 0x2f80, 0xef41,
             0x2d00, 0xedc1, 0xec81, 0x2c40, 0xe401, 0x24c0, 0x2580, 0xe541, 0x2700,
             0xe7c1, 0xe681, 0x2640, 0x2200, 0xe2c1, 0xe381, 0x2340, 0xe101, 0x21c0,
             0x2080, 0xe041, 0xa001, 0x60c0, 0x6180, 0xa141, 0x6300, 0xa3c1, 0xa281,
             0x6240, 0x6600, 0xa6c1, 0xa781, 0x6740, 0xa501, 0x65c0, 0x6480, 0xa441,
             0x6c00, 0xacc1, 0xad81, 0x6d40, 0xaf01, 0x6fc0, 0x6e80, 0xae41, 0xaa01,
             0x6ac0, 0x6b80, 0xab41, 0x6900, 0xa9c1, 0xa881, 0x6840, 0x7800, 0xb8c1,
             0xb981, 0x7940, 0xbb01, 0x7bc0, 0x7a80, 0xba41, 0xbe01, 0x7ec0, 0x7f80,
             0xbf41, 0x7d00, 0xbdc1, 0xbc81, 0x7c40, 0xb401, 0x74c0, 0x7580, 0xb541,
             0x7700, 0xb7c1, 0xb681, 0x7640, 0x7200, 0xb2c1, 0xb381, 0x7340, 0xb101,
             0x71c0, 0x7080, 0xb041, 0x5000, 0x90c1, 0x9181, 0x5140, 0x9301, 0x53c0,
             0x5280, 0x9241, 0x9601, 0x56c0, 0x5780, 0x9741, 0x5500, 0x95c1, 0x9481,
             0x5440, 0x9c01, 0x5cc0, 0x5d80, 0x9d41, 0x5f00, 0x9fc1, 0x9e81, 0x5e40,
             0x5a00, 0x9ac1, 0x9b81, 0x5b40, 0x9901, 0x59c0, 0x5880, 0x9841, 0x8801,
             0x48c0, 0x4980, 0x8941, 0x4b00, 0x8bc1, 0x8a81, 0x4a40, 0x4e00, 0x8ec1,
             0x8f81, 0x4f40, 0x8d01, 0x4dc0, 0x4c80, 0x8c41, 0x4400, 0x84c1, 0x8581,
             0x4540, 0x8701, 0x47c0, 0x4680, 0x8641, 0x8201, 0x42c0, 0x4380, 0x8341,
             0x4100, 0x81c1, 0x8081, 0x4040]

def usb_crc16(data):
    crc = 0xffff

    for b in data:
        crc = (crc >> 8) ^ crc16_tbl[(crc ^ b) & 0xff]

    return crc ^ 0xffff

@dataclass
class dpdm_sample:
    dp:      int = 0
    dm:      int = 0
    next_tm: float = 0

    def __init__(self, next_tm):
        self.next_tm = next_tm

class dpdm_byte:
    nr_bits:  int = 0
    b:        int = 0

@dataclass
class dpdm_data:
    byte:      dpdm_byte = field(default_factory=dpdm_byte)
    prev_bit:  int = None
    bytes_arr: list[int] = field(default_factory=list)

usage = "Usage: %prog [OPTIONS] FILE"
parser = OptionParser(usage=usage,
                      description="Reads CSV file with USB protocol extracted from oscilloscope by the `ds1054z` tool")
parser.add_option("-s", "--speed", type="string", default="auto",
                  dest="speed", help='Speed of the device. Accepts "low", "full" or "auto".')
options, args = parser.parse_args()

if len(args) == 0:
    parser.print_help()
    sys.exit(1)
else:
    filename = args[0]

f_input = open(filename)
csv_input = csv.reader(f_input, skipinitialspace=True)
header = next(csv_input)

FS_SYNC = 0x2a
LS_SYNC = 0xd5

PID_OUT   = 0xe1
PID_IN    = 0x69
PID_SOF   = 0xa5
PID_SETUP = 0x2d
PID_DATA0 = 0xc3
PID_DATA1 = 0x4b
PID_ACK   = 0xd2
PID_NAK   = 0x5a
PID_STALL = 0x1e
PID_PRE   = 0x3c

SE0 = -1
SE1 =  2

LOW  = -1
HIGH =  1

UNKNOWN      = 0
IDLE         = 1
DETECT_SYNC  = 2
RECEIVE      = 3
GOT_SE1      = 4
GOT_EOP      = 5

state = UNKNOWN
se0_cnt = 0

full_speed = None
if options.speed == "low":
    full_speed = False
elif options.speed == "full":
    full_speed = True

period = None
sample = None
data = None
prev_tm = None
prev_dp = None
prev_dm = None

for v1, v2, v3 in csv_input:
    tm_v = float(v1)
    dp_v = float(v2)
    dm_v = float(v3)

    # To logical levels
    dp_v = LOW if dp_v < 1.2 else HIGH
    dm_v = LOW if dm_v < 1.2 else HIGH

    # Detect full/low speed
    if full_speed is None and dp_v != dm_v:
        full_speed = (dp_v == HIGH)

    # Detect required number of samples per USB period
    if full_speed is not None and \
       period is None and prev_tm is not None:
        period = usb_period(full_speed)
        state = IDLE

    # Detect SYNC
    if state == IDLE and (prev_dp != dp_v or prev_dm != dm_v):
        state = DETECT_SYNC
        sample = dpdm_sample(tm_v + period)
        data = dpdm_data()

    # Oversampling and decoding
    if sample is not None:
        sample.dp  += dp_v
        sample.dm  += dm_v

        if tm_v >= sample.next_tm:
            dp = 1 if sample.dp > 0 else 0
            dm = 1 if sample.dm > 0 else 0

            # Detect EOP or SE1
            if dp != dm:
                if se0_cnt >= 2:
                    # EOP: detect J which follows the 2x SE0
                    if full_speed and dp > dm:
                        state = GOT_EOP
                    elif not full_speed and dp < dm:
                        state = GOT_EOP
                se0_cnt = 0
            elif dp == 0 and dm == 0:
                se0_cnt += 1
            else:
                print("[%f] Warning: SE1 state detected" % tm_v)
                state = GOT_SE1

            # SE1 or EOP
            if state == GOT_SE1 or state == GOT_EOP:
                sample = None
                if state == GOT_SE1:
                    # Discard everything and start over
                    data = None
                    state = IDLE
            else:
                # Decode a bit
                bit = raw_bit = 1 if dp > dm else 0
                if data.prev_bit is not None:
                    # Decode NRZI
                    bit = 1 if data.prev_bit == raw_bit else 0
                    data.prev_bit = raw_bit
                data.byte.b |= (bit << data.byte.nr_bits)
                data.byte.nr_bits += 1
                if data.byte.nr_bits == 8:
                    # Last bit of SYNC for further NRZI decoding
                    if state == DETECT_SYNC:
                        data.prev_bit = raw_bit
                    data.bytes_arr.append(data.byte.b)
                    data.byte = dpdm_byte()

                next_tm = sample.next_tm + period
                sample = dpdm_sample(next_tm)

    # Detect SYNC
    if state == DETECT_SYNC:
        if len(data.bytes_arr) == 1:
            sync = data.bytes_arr[0]
            if full_speed and sync == FS_SYNC:
                data.byte = dpdm_byte()
                state = RECEIVE
            elif not full_speed and sync == LS_SYNC:
                data.byte = dpdm_byte()
                state = RECEIVE
            else:
                # Incorrect sync so start over
                state = IDLE
                sample = None
                data = None

    # We have a full packet
    if state == GOT_EOP:
        if len(data.bytes_arr) > 1:
            if data.bytes_arr[1] == PID_SOF:
                nr_frame = ((data.bytes_arr[3] & 7) << 8) | data.bytes_arr[2]
                crc = ((data.bytes_arr[3] >> 3) & 0x1f)
                print("  SOF | NRFRAME %d | CRC5 0x%x (%s) | -> " %
                      (nr_frame, crc, "OK" if usb_crc5(nr_frame) == crc else "ERR"),
                      end='')
            elif data.bytes_arr[1] == PID_SETUP or \
                 data.bytes_arr[1] == PID_IN:
                pid = "SETUP" if data.bytes_arr[1] == PID_SETUP else "IN"
                addrendp = ((data.bytes_arr[3] & 7) << 8) | data.bytes_arr[2]
                addr = (data.bytes_arr[2] & 0x7f)
                endp = ((data.bytes_arr[3] & 7) << 1) | ((data.bytes_arr[2] & 0x80) >> 7)
                crc = ((data.bytes_arr[3] >> 3) & 0x1f)

                print("%5s | ADDR %d | ENDP %d | CRC5 0x%x (%s) | -> " %
                      (pid, addr, endp, crc, "OK" if usb_crc5(addrendp) == crc else "ERR"),
                      end='')

            elif data.bytes_arr[1] == PID_DATA0:
                crc = (data.bytes_arr[-1] << 8) | data.bytes_arr[-2]
                data0 = " ".join(["%x" % v for v in data.bytes_arr[2:-2]])

                print("DATA0 | %s | CRC16 0x%x (%s) | -> " %
                      (data0, crc, "OK" if usb_crc16(data.bytes_arr[2:-2]) == crc else "ERR"),
                      end='')

            elif data.bytes_arr[1] == PID_ACK:
                print("  ACK | -> ", end='')

            elif data.bytes_arr[1] == PID_STALL:
                print("STALL | -> ", end='')

            print("[", end='')
            for i, b in enumerate(data.bytes_arr):
                print("%x%s" % (b, (' ' if i + 1 < len(data.bytes_arr) else '')),
                      end='')
            print(']')

        state = IDLE
        sample = None
        data = None

    prev_tm = tm_v
    prev_dp = dp_v
    prev_dm = dm_v
