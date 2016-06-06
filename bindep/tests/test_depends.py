# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import subprocess
from textwrap import dedent

import fixtures
import mock
import ometa.runtime
from testtools.matchers import Contains
from testtools.matchers import Equals
from testtools.matchers import MatchesSetwise
from testtools import TestCase

from bindep.depends import _eval
from bindep.depends import Depends
from bindep.depends import Dpkg
from bindep.depends import Emerge
from bindep.depends import Rpm


# NOTE(notmorgan): In python3 subprocess.check_output returns bytes not
# string. All mock calls for subprocess.check_output have been updated to
# ensure bytes is used over string. In python 2 this is a no-op change.


class TestDepends(TestCase):

    def test_empty_file(self):
        depends = Depends("")
        self.assertEqual([], depends.profiles())

    def test_platform_profiles_succeeds(self):
        depends = Depends("")
        self.assertIsInstance(depends.platform_profiles(), list)

    @contextlib.contextmanager
    def _mock_lsb(self, platform):
        r_val = "%s\n14.04\ntrusty\n" % platform
        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(
                subprocess,
                'check_output',
                return_value=r_val.encode('utf-8'))).mock
        yield mock_checkoutput
        mock_checkoutput.assert_called_once_with(["lsb_release", "-cirs"],
                                                 stderr=subprocess.STDOUT)

    def test_detects_centos(self):
        with self._mock_lsb("CentOS"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:centos"))

    def test_detects_fedora(self):
        with self._mock_lsb("Fedora"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:fedora"))

    def test_detects_opensuse(self):
        with self._mock_lsb("openSUSE"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:opensuse"))

    def test_detects_suse_linux(self):
        with self._mock_lsb("SUSE Linux"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:suselinux"))

    def test_detects_ubuntu(self):
        with self._mock_lsb("Ubuntu"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:ubuntu"))

    def test_detects_release(self):
        with self._mock_lsb("Ubuntu"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:ubuntu-14"))

    def test_detects_subrelease(self):
        with self._mock_lsb("Ubuntu"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:ubuntu-14.04"))

    def test_detects_codename(self):
        with self._mock_lsb("Ubuntu"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(),
                Contains("platform:ubuntu-trusty"))

    def test_centos_implies_rpm(self):
        with self._mock_lsb("CentOS"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:rpm"))
            self.assertIsInstance(depends.platform, Rpm)

    def test_fedora_implies_rpm(self):
        with self._mock_lsb("Fedora"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:rpm"))
            self.assertIsInstance(depends.platform, Rpm)

    def test_opensuse_implies_rpm(self):
        with self._mock_lsb("openSUSE"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:rpm"))
            self.assertIsInstance(depends.platform, Rpm)

    def test_suse_linux_implies_rpm(self):
        with self._mock_lsb("SUSE LINUX"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:rpm"))
            self.assertIsInstance(depends.platform, Rpm)

    def test_ubuntu_implies_dpkg(self):
        with self._mock_lsb("Ubuntu"):
            depends = Depends("")
            self.assertThat(
                depends.platform_profiles(), Contains("platform:dpkg"))
            self.assertIsInstance(depends.platform, Dpkg)

    def test_finds_profiles(self):
        depends = Depends(dedent("""\
            foo
            bar [something]
            quux [anotherthing !nothing] <=12
            """))
        self.assertThat(
            depends.profiles(),
            MatchesSetwise(*map(
                Equals, ["something", "anotherthing", "nothing"])))

    def test_empty_rules(self):
        depends = Depends("")
        self.assertEqual([], depends._rules)

    def test_selectors(self):
        depends = Depends("foo [!bar baz quux]\n")
        self.assertEqual(
            [("foo", [(False, "bar"), (True, "baz"), (True, "quux")], [])],
            depends._rules)

    def test_versions(self):
        depends = Depends("foo <=1,!=2\n")
        self.assertEqual(
            [("foo", [], [('<=', '1'), ('!=', '2')])],
            depends._rules)

    def test_no_selector_active(self):
        depends = Depends("foo\n")
        self.assertEqual([("foo", [], [])], depends.active_rules(["default"]))

    def test_negative_selector_removes_rule(self):
        depends = Depends("foo [!off]\n")
        self.assertEqual([], depends.active_rules(["on", "off"]))

    def test_positive_selector_includes_rule(self):
        depends = Depends("foo [on]\n")
        self.assertEqual(
            [("foo", [(True, "on")], [])],
            depends.active_rules(["on", "off"]))

    def test_positive_selector_not_in_profiles_inactive(self):
        depends = Depends("foo [on]\n")
        self.assertEqual([], depends.active_rules(["default"]))

    def test_check_rule_missing(self):
        depends = Depends("")
        depends.platform = mock.MagicMock()
        mock_depend_platform = self.useFixture(
            fixtures.MockPatchObject(depends.platform, 'get_pkg_version',
                                     return_value=None)).mock
        self.assertEqual(
            [('missing', ['foo'])], depends.check_rules([("foo", [], [])]))
        mock_depend_platform.assert_called_once_with("foo")

    def test_check_rule_present(self):
        depends = Depends("")
        depends.platform = mock.MagicMock()
        mock_depend_platform = self.useFixture(
            fixtures.MockPatchObject(depends.platform, 'get_pkg_version',
                                     return_value="123")).mock
        self.assertEqual([], depends.check_rules([("foo", [], [])]))
        mock_depend_platform.assert_called_once_with("foo")

    def test_check_rule_incompatible(self):
        depends = Depends("")
        depends.platform = mock.MagicMock()
        depends.platform = mock.MagicMock()
        mock_depend_platform = self.useFixture(
            fixtures.MockPatchObject(depends.platform, 'get_pkg_version',
                                     return_value="123")).mock
        self.assertEqual(
            [('badversion', [('foo', "!=123", "123")])],
            depends.check_rules([("foo", [], [("!=", "123")])]))
        mock_depend_platform.assert_called_once_with("foo")

    def test_parser_patterns(self):
        depends = Depends(dedent("""\
            foo
            bar [something]
            category/packagename # for gentoo
            baz [platform:this platform:that-those]
            quux [anotherthing !nothing] <=12
            womp # and a comment
            # a standalone comment and a blank line

            # all's ok? good then
            """))
        self.assertEqual(len(depends.active_rules(['default'])), 3)

    def test_parser_invalid(self):
        self.assertRaises(ometa.runtime.ParseError,
                          lambda: Depends("foo [platform:bar@baz]\n"))


class TestDpkg(TestCase):

    def test_not_installed(self):
        platform = Dpkg()
        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(
                subprocess,
                'check_output',
                return_value=b"foo deinstall ok config-files 4.0.0-0ubuntu1\n")
        ).mock
        self.assertEqual(None, platform.get_pkg_version("foo"))
        mock_checkoutput.assert_called_once_with(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT)

    def test_unknown_package(self):
        platform = Dpkg()
        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output')).mock

        def _side_effect_raise(*args, **kwargs):
            raise subprocess.CalledProcessError(
                1, [], "dpkg-query: no packages found matching foo\n")

        mock_checkoutput.side_effect = _side_effect_raise
        self.assertEqual(None, platform.get_pkg_version("foo"))
        mock_checkoutput.assert_called_once_with(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT)

    def test_installed_version(self):
        platform = Dpkg()
        mocked_checkoutput = self.useFixture(
            fixtures.MockPatchObject(
                subprocess,
                'check_output',
                return_value=b"foo install ok installed 4.0.0-0ubuntu1\n")
        ).mock
        self.assertEqual("4.0.0-0ubuntu1", platform.get_pkg_version("foo"))
        mocked_checkoutput.assert_called_once_with(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT)


class TestEmerge(TestCase):

    def test_not_installed(self):
        platform = Emerge()

        def _side_effect_raise(*args, **kwargs):
            raise subprocess.CalledProcessError(3, [], '')

        mocked_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output')).mock

        mocked_checkoutput.side_effect = _side_effect_raise
        self.assertEqual(None, platform.get_pkg_version("foo"))
        mocked_checkoutput.assert_called_once_with(
            ['equery', 'l', '--format=\'$version\'', 'foo'],
            stderr=subprocess.STDOUT)

    def test_unknown_package(self):
        platform = Emerge()

        def _side_effect_raise(*args, **kwargs):
            raise subprocess.CalledProcessError(3, [], '')

        mocked_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output')).mock

        mocked_checkoutput.side_effect = _side_effect_raise
        self.assertEqual(None, platform.get_pkg_version("foo"))
        mocked_checkoutput.assert_called_once_with(
            ['equery', 'l', '--format=\'$version\'', 'foo'],
            stderr=subprocess.STDOUT)

    def test_installed_version(self):
        platform = Emerge()
        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output',
                                     return_value=b"4.0.0\n")).mock
        self.assertEqual("4.0.0", platform.get_pkg_version("foo"))
        mock_checkoutput.assert_called_once_with(
            ['equery', 'l', '--format=\'$version\'', 'foo'],
            stderr=subprocess.STDOUT)


class TestRpm(TestCase):

    # NOTE: test_not_installed is not implemented as rpm seems to only be aware
    # of installed packages

    def test_unknown_package(self):
        platform = Rpm()

        def _side_effect_raise(*args, **kwargs):
            raise subprocess.CalledProcessError(
                1, [], "package foo is not installed\n")

        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output')).mock
        mock_checkoutput.side_effect = _side_effect_raise
        self.assertEqual(None, platform.get_pkg_version("foo"))
        mock_checkoutput.assert_called_once_with(
            ["rpm", "--qf",
             "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n", "-q",
             "foo"],
            stderr=subprocess.STDOUT)
        self.assertEqual(None, platform.get_pkg_version("foo"))

    def test_installed_version(self):
        platform = Rpm()
        mock_checkoutput = self.useFixture(
            fixtures.MockPatchObject(subprocess, 'check_output',
                                     return_value=b"foo 4.0.0-0.el6\n")).mock
        self.assertEqual("4.0.0-0.el6", platform.get_pkg_version("foo"))
        mock_checkoutput.assert_called_once_with(
            ["rpm", "--qf",
             "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n", "-q",
             "foo"],
            stderr=subprocess.STDOUT)


class TestEval(TestCase):

    def test_lt(self):
        self.assertEqual(True, _eval("3.5-ubuntu", "<", "4"))
        self.assertEqual(False, _eval("4", "<", "3.5-ubuntu"))
        self.assertEqual(False, _eval("4", "<", "4"))
        # Epoch comes first
        self.assertEqual(True, _eval("1:2", "<", "2:1"))
        # ~'s
        self.assertEqual(True, _eval("1~~", "<", "1~~a"))
        self.assertEqual(True, _eval("1~~a", "<", "1~"))
        self.assertEqual(True, _eval("1~", "<", "1"))
        self.assertEqual(True, _eval("1", "<", "1a"))
        # debver's
        self.assertEqual(True, _eval("1-a~~", "<", "1-a~~a"))
        self.assertEqual(True, _eval("1-a~~a", "<", "1-a~"))
        self.assertEqual(True, _eval("1-a~", "<", "1-a"))
        self.assertEqual(True, _eval("1-a", "<", "1-aa"))
        # end-of-segment
        self.assertEqual(True, _eval("1a", "<", "1aa"))
        self.assertEqual(True, _eval("1a-a", "<", "1a-aa"))

    def test_lte(self):
        self.assertEqual(True, _eval("3.5-ubuntu", "<=", "4"))
        self.assertEqual(False, _eval("4", "<=", "3.5-ubuntu"))
        self.assertEqual(True, _eval("4", "<=", "4"))

    def test_eq(self):
        self.assertEqual(True, _eval("3.5-ubuntu", "==", "3.5-ubuntu"))
        self.assertEqual(False, _eval("4", "==", "3.5-ubuntu"))
        self.assertEqual(False, _eval("3.5-ubuntu", "==", "4"))

    def test_neq(self):
        self.assertEqual(False, _eval("3.5-ubuntu", "!=", "3.5-ubuntu"))
        self.assertEqual(True, _eval("4", "!=", "3.5-ubuntu"))
        self.assertEqual(True, _eval("3.5-ubuntu", "!=", "4"))

    def test_gt(self):
        self.assertEqual(False, _eval("3.5-ubuntu", ">", "4"))
        self.assertEqual(True, _eval("4", ">", "3.5-ubuntu"))
        self.assertEqual(False, _eval("4", ">", "4"))

    def test_gte(self):
        self.assertEqual(False, _eval("3.5-ubuntu", ">=", "4"))
        self.assertEqual(True, _eval("4", ">=", "3.5-ubuntu"))
        self.assertEqual(True, _eval("4", ">=", "4"))
