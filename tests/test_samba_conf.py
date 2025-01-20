import textwrap
import unittest
import os.path as osp
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
            conf.section("share4", create=False)

    def test_parse_invalid(self):
        with self.assertRaises(samba_conf._ParseError):
            samba_conf._parse_conf("[[share1]")
        with self.assertRaises(samba_conf._ParseError):
            samba_conf._parse_conf("prop1")


class TestTransformations(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.maxDiff = None

    def compare(self, expected, params):
        with open(osp.join(osp.dirname(__file__), "testdata", "00_original.conf"), "rt") as f:
            conf = samba_conf._parse_conf(f.read())
        section = params["section"]
        state = params["state"]
        option = params["option"]
        value = params["value"]
        samba_conf._apply_transformations(conf, section, state, option, value)
        with open(osp.join(osp.dirname(__file__), "testdata", expected), "rt") as f:
            # open("foo.conf", "wt").write(conf.stringify())
            self.assertEqual(conf.stringify(), f.read())

    def test_add_section(self):
        self.compare(
            "01_add_section.conf",
            params=dict(
                section="tank",
                state="present",
                option="foo",
                value="bar",
            ),
        )

    def test_comment_section(self):
        self.compare(
            "02_comment_section.conf",
            params=dict(
                section="global",
                state="commented",
                option=None,
                value=None,
            ),
        )

    def test_uncomment_section(self):
        self.compare(
            "03_uncomment_section.conf",
            params=dict(
                section="netlogon",
                state="present",
                option=None,
                value=None,
            ),
        )
