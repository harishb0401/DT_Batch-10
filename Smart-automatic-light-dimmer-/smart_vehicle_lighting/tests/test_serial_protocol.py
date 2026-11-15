"""
Unit Tests for Serial Protocol Parsing
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.serial_communication import SerialCommunicator

class TestSerialProtocol(unittest.TestCase):
    def setUp(self):
        self.config = {
            "serial": {
                "port": "COM_TEST",
                "baudrate": 115200,
                "mock_serial_on_failure": True
            }
        }
        self.comm = SerialCommunicator(self.config)

    def test_parse_valid_telemetry(self):
        line = "DATA:LDR=DARK,BEAM=NORMAL,SRC=REMOTE"
        self.comm._parse_line(line)
        self.assertEqual(self.comm.latest_ldr_state, "DARK")
        self.assertEqual(self.comm.latest_hardware_beam, "NORMAL")
        self.assertEqual(self.comm.latest_control_source, "REMOTE")

    def test_parse_telemetry_with_high_ambient(self):
        line = "DATA:LDR=HIGH,BEAM=LOW,SRC=LOCAL"
        self.comm._parse_line(line)
        self.assertEqual(self.comm.latest_ldr_state, "HIGH")
        self.assertEqual(self.comm.latest_hardware_beam, "LOW")
        self.assertEqual(self.comm.latest_control_source, "LOCAL")

    def test_parse_acknowledgments(self):
        self.comm._parse_line("ACK:LOW")
        self.assertEqual(self.comm.last_ack, "ACK:LOW")
        self.comm._parse_line("ACK:NORMAL")
        self.assertEqual(self.comm.last_ack, "ACK:NORMAL")

    def test_mock_set_beam_simulation(self):
        self.comm._is_mock = True
        self.comm.set_beam("LOW")
        self.assertEqual(self.comm.latest_hardware_beam, "LOW")
        self.comm.set_beam("NORMAL")
        self.assertEqual(self.comm.latest_hardware_beam, "NORMAL")

if __name__ == "__main__":
    unittest.main()
