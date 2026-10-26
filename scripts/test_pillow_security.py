"""Safe regression check for GHSA-65qm-jvmh-6pqg (no oversized allocation)."""

import io
import struct
import unittest

from PIL import Image


class PillowSecurityTest(unittest.TestCase):
    def test_rejected_gif_frame_preserves_size(self):
        # Advisory fixture: a valid 1x1 frame followed by an oversized extent.
        # Never retry seek/load after rejection: vulnerable Pillow would allocate GBs.
        frame = b"," + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + b"\x02\x02\x44\x01\x00"
        gif = (
            b"GIF89a"
            + struct.pack("<HHBBB", 1, 1, 0x80, 0, 0)
            + b"\x00" * 3
            + b"\xff" * 3
            + frame
            + b"," + struct.pack("<HHHHB", 0, 0, 40000, 40000, 0)
            + frame
            + b";"
        )
        with Image.open(io.BytesIO(gif)) as image:
            self.assertEqual(image.size, (1, 1))
            with self.assertRaises(Image.DecompressionBombError):
                image.seek(1)
            self.assertEqual(image.size, (1, 1))


if __name__ == "__main__":
    unittest.main()
