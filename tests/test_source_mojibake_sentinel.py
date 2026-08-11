from __future__ import absolute_import

from pathlib import Path
import unittest


SCAN_ROOTS = ["asset_forge", "scripts", "tests", "config", "Plugins"]
SCAN_EXTENSIONS = {".py", ".json", ".md", ".txt"}


def mojibake_markers():
    return [
        chr(0x3F) * 4,
        chr(0x704F),
        chr(0x8930),
        chr(0x59E3) + chr(0x5D86) + chr(0x6F57),
        chr(0x5A34) + chr(0x5B2D) + chr(0x762F),
        chr(0x59DD) + chr(0xFF45) + chr(0x7D21),
        chr(0x93C4),
        chr(0x9343),
        chr(0x7EBE),
        chr(0x6748),
        chr(0x7487),
        chr(0x7F01),
        chr(0x9286),
        chr(0x951B),
        chr(0x4E68),
        chr(0x6C9C),
        chr(0x8BF2),
        chr(0x59DE),
        chr(0x7D11),
        chr(0x5241),
        chr(0x6FEE),
        chr(0x9426),
        chr(0x95B8),
        chr(0x9420),
        chr(0x95B9),
        chr(0x940E),
        chr(0x93B5),
        chr(0x7035),
        chr(0x95C3),
        chr(0x74A7),
        chr(0x93C3),
        chr(0x7D21),
    ]


def marker_from_codes(*codes):
    return "".join(chr(code) for code in codes)


def mojibake_from_text_codes(*codes):
    return marker_from_codes(*codes).encode("utf-8").decode("gbk", "ignore")


def source_mojibake_markers():
    return mojibake_markers() + [
        chr(0x5BB8),
        chr(0x6DC7),
        chr(0x6960),
        chr(0x9340),
        chr(0x7CA8),
        chr(0x7468),
        chr(0x7EDB),
        chr(0x95C3),
        marker_from_codes(0x5B2D, 0x7487),
        marker_from_codes(0x30E4, 0x7DBC),
        marker_from_codes(0x9340, 0x544A, 0x5C7C),
        mojibake_from_text_codes(0x5F53, 0x524D),
        mojibake_from_text_codes(0x73AF, 0x5883),
        mojibake_from_text_codes(0x62A5, 0x544A),
        mojibake_from_text_codes(0x914D, 0x7F6E),
        mojibake_from_text_codes(0x540C, 0x540D),
        mojibake_from_text_codes(0x7B56, 0x7565),
        mojibake_from_text_codes(0x65E0, 0x6CD5),
        mojibake_from_text_codes(0x5BFC, 0x5165),
        mojibake_from_text_codes(0x8D44, 0x4EA7),
        mojibake_from_text_codes(0x76EE, 0x5F55),
        mojibake_from_text_codes(0x9A8C, 0x8BC1),
        mojibake_from_text_codes(0x4FEE, 0x590D),
        mojibake_from_text_codes(0x4E2D, 0x6587),
        mojibake_from_text_codes(0x6D4B, 0x8BD5),
        mojibake_from_text_codes(0x6B63, 0x5F0F),
        mojibake_from_text_codes(0x65E5, 0x5FD7),
        mojibake_from_text_codes(0x8DEF, 0x5F84),
        mojibake_from_text_codes(0x53EF, 0x751F, 0x6210),
        mojibake_from_text_codes(0x6750, 0x8D28),
    ]


def portfolio_user_text_mojibake_markers():
    return [
        mojibake_from_text_codes(0x4F5C, 0x54C1),
        mojibake_from_text_codes(0x8865, 0x771F, 0x5B9E),
        mojibake_from_text_codes(0x622A, 0x56FE),
        mojibake_from_text_codes(0x5F55, 0x5C4F),
        mojibake_from_text_codes(0x5F55, 0x5236),
        mojibake_from_text_codes(0x73B0, 0x573A),
        mojibake_from_text_codes(0x4E0B, 0x4E00, 0x6B65),
        mojibake_from_text_codes(0x5C01, 0x9876),
        mojibake_from_text_codes(0x79BB, 0x7EBF, 0x62A5, 0x544A),
        mojibake_from_text_codes(0x6750, 0x8D28),
        mojibake_from_text_codes(0x8BC1, 0x636E),
        mojibake_from_text_codes(0x53EF, 0x8FFD, 0x8E2A),
        mojibake_from_text_codes(0x5E72, 0x51C0, 0x5DE5, 0x7A0B),
        mojibake_from_text_codes(0x5173, 0x95ED),
        mojibake_from_text_codes(0x9A8C, 0x6536),
        mojibake_from_text_codes(0x5BFC, 0x51FA),
        mojibake_from_text_codes(0x963B, 0x65AD),
        mojibake_from_text_codes(0x626B, 0x63CF),
        mojibake_from_text_codes(0x63D0, 0x793A),
    ]


class SourceMojibakeSentinelTest(unittest.TestCase):
    def test_source_and_tests_do_not_contain_common_mojibake_markers(self):
        offenders = []
        markers = source_mojibake_markers()
        for root_name in SCAN_ROOTS:
            root = Path(root_name)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in SCAN_EXTENSIONS:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                found = [marker for marker in markers if marker in text]
                if found:
                    offenders.append("{0}: {1}".format(path.as_posix(), [marker.encode("unicode_escape").decode("ascii") for marker in found]))
        self.assertEqual(offenders, [])

    def test_texture_set_user_copy_does_not_use_legacy_token_name(self):
        offenders = []
        forbidden = "贴图集 " + "Token"
        for root_name in ["asset_forge", "tests"]:
            root = Path(root_name)
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if forbidden in text:
                    offenders.append(path.as_posix())
        self.assertEqual(offenders, [])

    def test_portfolio_user_text_does_not_contain_common_mojibake_fragments(self):
        offenders = []
        markers = portfolio_user_text_mojibake_markers()
        for root_name in ["asset_forge", "scripts", "tests", "config"]:
            root = Path(root_name)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in SCAN_EXTENSIONS:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                found = [marker for marker in markers if marker in text]
                if found:
                    offenders.append("{0}: {1}".format(path.as_posix(), [marker.encode("unicode_escape").decode("ascii") for marker in found]))
        self.assertEqual(offenders, [])

if __name__ == "__main__":
    unittest.main()
