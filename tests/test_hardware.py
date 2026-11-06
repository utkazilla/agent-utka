import unittest
from unittest.mock import patch

from copilot.hardware import GpuMemory, read_vram


class HardwareTests(unittest.TestCase):
    @patch("copilot.hardware.subprocess.check_output")
    def test_reports_free_memory_per_gpu_and_skips_unavailable_values(self, command):
        command.return_value = "RTX A, 12282, 4336\nRTX B, 8192, 112\nUnknown, N/A, N/A\n"
        self.assertEqual(read_vram(), [GpuMemory("RTX A", 12282, 4336), GpuMemory("RTX B", 8192, 112)])
        self.assertIn("--query-gpu=name,memory.total,memory.free", command.call_args.args[0])

    @patch("copilot.hardware.subprocess.check_output", side_effect=FileNotFoundError)
    def test_no_supported_gpu_probe_returns_unavailable(self, _command):
        self.assertEqual(read_vram(), [])
