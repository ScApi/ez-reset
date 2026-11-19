import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ez_reset.devices import Device
from ez_reset.printer import Printer
from ez_reset.status import MaintenanceBoxState, Status


def status_payload(*fields):
    body = b"".join(bytes((header, len(value))) + value for header, value in fields)
    return len(body).to_bytes(2, "little") + body


class FakeControl:
    def __init__(self, status, rw_response=b"rw:01:OK;"):
        self.status = status
        self.rw_response = rw_response
        self.commands = []

    def send(self, command):
        self.commands.append(command)
        if command[:2] == b"st":
            return b"@BDC ST2\r\n" + self.status
        if command[:2] == b"rw":
            return self.rw_response
        raise AssertionError(f"Unexpected command: {command!r}")

    def identify(self):
        return "MDL:ET-2810;SN:TEST123;"


class StatusTemporaryResetTests(unittest.TestCase):
    def test_serial_is_decoded_and_maintenance_box_state_is_parsed(self):
        raw = status_payload(
            (0x40, b"ABC123456"),
            (0x37, bytes((2, 2, 7, 1, 3))),
        )
        status = Status.from_bytes(raw)

        self.assertEqual(status.serial, "ABC123456")
        self.assertEqual(len(status.maintenance_box_info), 2)
        self.assertIs(status.maintenance_box_info[0].state, MaintenanceBoxState.FULL)
        self.assertEqual(status.maintenance_box_info[0].reset_count, 7)
        self.assertIs(status.maintenance_box_info[1].state, MaintenanceBoxState.NEAR_FULL)
        self.assertEqual(status.maintenance_box_info[1].reset_count, 3)

    def test_one_byte_maintenance_box_state_is_supported(self):
        raw = status_payload((0x37, bytes((1, 0))))
        status = Status.from_bytes(raw)
        self.assertEqual(len(status.maintenance_box_info), 1)
        self.assertIs(status.maintenance_box_info[0].state, MaintenanceBoxState.NOT_FULL)
        self.assertIsNone(status.maintenance_box_info[0].reset_count)


class TemporaryWasteResetTests(unittest.TestCase):
    @staticmethod
    def printer(status, response=b"rw:01:OK;"):
        control = FakeControl(status, response)
        device = Device(model=b"", key=b"", counters=[], reset={})
        return Printer(control, device), control

    def test_sends_documented_rw_frame_only_after_full_box_status(self):
        serial = "ABC123456"
        raw = status_payload(
            (0x40, serial.encode("ascii")),
            (0x37, bytes((2, 2, 4))),
        )
        printer, control = self.printer(raw)

        self.assertTrue(printer.temporary_reset_waste())

        self.assertEqual(control.commands[0], b"st\x01\x00\x01")
        payload = struct.pack("<H", 1) + hashlib.sha1(serial.encode("ascii")).digest()
        expected = b"rw" + len(payload).to_bytes(2, "little") + payload
        self.assertEqual(control.commands[1], expected)
        self.assertEqual(len(control.commands), 2)

    def test_does_not_send_rw_when_maintenance_box_is_not_full(self):
        raw = status_payload(
            (0x40, b"ABC123456"),
            (0x37, bytes((1, 0))),
        )
        printer, control = self.printer(raw)

        with self.assertRaisesRegex(ValueError, "does not report a full"):
            printer.temporary_reset_waste()

        self.assertEqual(len(control.commands), 1)

    def test_does_not_send_rw_without_serial_number(self):
        raw = status_payload((0x37, bytes((1, 2))))
        printer, control = self.printer(raw)

        with self.assertRaisesRegex(ValueError, "usable serial number"):
            printer.temporary_reset_waste()

        self.assertEqual(len(control.commands), 1)

    def test_requires_explicit_printer_acknowledgement(self):
        raw = status_payload(
            (0x40, b"ABC123456"),
            (0x37, bytes((1, 2))),
        )
        printer, _control = self.printer(raw, b"rw:01:ERROR;")
        self.assertFalse(printer.temporary_reset_waste())


if __name__ == "__main__":
    unittest.main()
