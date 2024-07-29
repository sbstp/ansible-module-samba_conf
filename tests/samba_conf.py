import textwrap
import unittest
from library import samba_conf


class TestParsing(unittest.TestCase):
    def test_parse_ok(self):
        conf = samba_conf._parse_conf(
            textwrap.dedent(
                """\
                # this is a samba config file
                [share1]
                  prop1 = prop1
                  prop2=prop2
                  prop3= prop3
                  prop4 =prop4
                  prop5     =      prop5
                  ;prop6 =prop6
                [share2]
                  prop1 = prop1
                  prop2 =
                ;[share3]
                # hello
                ; world
                """
            )
        )
        self.assertEqual(conf._items[0].text, "# this is a samba config file")
        self.assertEqual(conf.option("share1", "prop1").value, "prop1")
        self.assertEqual(conf.option("share1", "prop2").value, "prop2")
        self.assertEqual(conf.option("share1", "prop3").value, "prop3")
        self.assertEqual(conf.option("share1", "prop4").value, "prop4")
        self.assertEqual(conf.option("share1", "prop5").value, "prop5")
        with self.assertRaises(KeyError):
            conf.option("share1", "prop6", create=False)
        self.assertEqual(conf.option("share2", "prop1").value, "prop1")
        self.assertEqual(conf.option("share2", "prop2").value, "")
        with self.assertRaises(KeyError):
            conf.section("share3", create=False)
        self.assertEqual(conf._items[-2].text, "# hello")
        self.assertEqual(conf._items[-1].text, "; world")

    def test_parse_invalid(self):
        with self.assertRaises(samba_conf._ParseError):
            samba_conf._parse_conf("[[share1]")
        with self.assertRaises(samba_conf._ParseError):
            samba_conf._parse_conf("prop1")
