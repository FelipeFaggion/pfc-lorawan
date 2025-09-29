# Copyright 2021 LeMaRiva|tech lemariva.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# RASPBERRY PI Pico 
device_config = {
    'spi_unit': 0,
    'miso':4,
    'mosi':3,
    'ss':5,
    'sck':2,
    'dio_0':9,
    'reset':8,
    'led':25, 
}


app_config = {
    'loop': 200,
    'sleep': 100,
}

lora_parameters = {
    'tx_power_level': 2, 
    'signal_bandwidth': 'SF7BW125',
    'spreading_factor': 7,    
    'coding_rate': 5, 
    'sync_word': 0x34, 
    'implicit_header': False,
    'preamble_length': 8,
    'enable_CRC': True,
    'invert_IQ': False,
}

wifi_config = {
    'ssid':'',
    'password':''
}

ttn_config = {
    'devaddr': bytearray([0x00, 0x22, 0x03, 0x01]),
    'nwkey': bytearray([0x56, 0x6B, 0x54, 0xED, 0x53, 0x05, 0x06, 0x2D, 0x86, 0xB4, 0xFB, 0x51, 0xD6, 0x9A, 0xDC, 0x84]),
    'app': bytearray([0x8A, 0x6B, 0xBD, 0xD1, 0x73, 0x45, 0x53, 0xFC, 0xC6, 0xDD, 0x97, 0x42, 0x26, 0x84, 0x85, 0xCC]),
    'country': 'AU',
}