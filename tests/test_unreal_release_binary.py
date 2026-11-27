import struct
import unittest

from scripts.verify_unreal_release_binary import path_indicators, verify_dll


def _fixture(*, debug_path=b"AssetForgeEditor.pdb", module_export=True, machine=0x8664):
    image = bytearray(0x800)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, 0x84, machine, 1, 0, 0, 0, 240, 0x2000)
    optional = 0x98
    struct.pack_into("<H", image, optional, 0x20B)
    struct.pack_into("<I", image, optional + 108, 16)
    struct.pack_into("<II", image, optional + 112, 0x1000, 0x88)
    struct.pack_into("<II", image, optional + 112 + 6 * 8, 0x1090, 28)
    struct.pack_into("<IIII", image, optional + 240 + 8, 0x400, 0x1000, 0x400, 0x200)
    struct.pack_into("<IIHHIIIIIII", image, 0x200, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0x1038, 0)
    struct.pack_into("<I", image, 0x238, 0x1050)
    export = b"ThisIsAnUnrealEngineModule" if module_export else b"AnotherExport"
    image[0x250:0x250 + len(export)] = export
    codeview = b"RSDS" + bytes(20) + debug_path + b"\x00"
    struct.pack_into("<IIHHIIII", image, 0x290, 0, 0, 0, 0, 2, len(codeview), 0x1110, 0x310)
    image[0x310:0x310 + len(codeview)] = codeview
    return bytes(image)


class TestUnrealReleaseBinary(unittest.TestCase):
    def test_reads_pe_module_export_and_basename_codeview(self):
        data = _fixture()
        result = verify_dll(data)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["machine"], "x64")
        self.assertEqual(result["type"], "PE32+ DLL")
        self.assertTrue(result["unreal_module_export"])
        self.assertEqual(result["codeview_record_count"], 1)
        self.assertEqual(result["private_path_strings"], 0)

    def test_rejects_a_debug_path_and_absent_module_export(self):
        result = verify_dll(_fixture(debug_path=b"Z:\\Builder\\symbols.pdb", module_export=False))
        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["unreal_module_export"])
        self.assertEqual(result["codeview_paths_with_directories"], 1)

    def test_rejects_a_non_x64_binary(self):
        with self.assertRaisesRegex(ValueError, r"x64 PE32\+ DLL"):
            verify_dll(_fixture(machine=0x14C))

    def test_finds_drive_and_unc_paths_in_narrow_and_unaligned_wide_strings(self):
        data = (b"\x00X:/Build/Foo.cpp\x00" + ("\0Y:\\构建\\素材.h\0").encode("utf-16-le")
                + b"\0\\\\BuildServer\\Share\\Source.cpp\0")
        found = path_indicators(data)
        self.assertTrue(any("x:/build/foo.cpp" in value for value in found))
        self.assertTrue(any("y:/构建/素材.h" in value for value in found))
        self.assertTrue(any("//buildserver/share/source.cpp" in value for value in found))

    def test_leaves_virtual_sources_and_https_links_to_the_product_intact(self):
        data = (b"\x00AssetForgeSource\\Plugin.cpp\x00UnrealEngineSource\\Core.h\x00"
                b"https://github.com/Elviszhuoyu/DCC-AssetForge\x00")
        self.assertFalse(path_indicators(data))
        result = verify_dll(_fixture() + data)
        self.assertEqual(result["mapped_diagnostic_paths"], {"assetforge": 1, "unreal": 1})

