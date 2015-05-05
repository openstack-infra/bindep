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

import subprocess
from textwrap import dedent

import mox
import ometa.runtime
from testtools.matchers import Contains
from testtools.matchers import Equals
from testtools.matchers import MatchesSetwise
from testtools import TestCase

from bindep.depends import _eval
from bindep.depends import Depends
from bindep.depends import Dpkg
from bindep.depends import Platform
from bindep.depends import Rpm


class TestDepends(TestCase):

    def test_empty_file(self):
        depends = Depends("")
        self.assertEqual([], depends.profiles())

    def test_platform_profiles_succeeds(self):
        depends = Depends("")
        self.assertIsInstance(depends.platform_profiles(), list)

    def _mock_lsb(self, platform):
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["lsb_release", "-cirs"],
            stderr=subprocess.STDOUT).AndReturn("%s\n14.04\ntrusty\n"
                                                % platform)
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)

    def test_detects_centos(self):
        self._mock_lsb("CentOS")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:centos"))

    def test_detects_fedora(self):
        self._mock_lsb("Fedora")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:fedora"))

    def test_detects_ubuntu(self):
        self._mock_lsb("Ubuntu")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:ubuntu"))

    def test_detects_release(self):
        self._mock_lsb("Ubuntu")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:ubuntu-14"))

    def test_detects_subrelease(self):
        self._mock_lsb("Ubuntu")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:ubuntu-14.04"))

    def test_detects_codename(self):
        self._mock_lsb("Ubuntu")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:ubuntu-trusty"))

    def test_centos_implies_rpm(self):
        self._mock_lsb("CentOS")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:rpm"))
        self.assertIsInstance(depends.platform, Rpm)

    def test_fedora_implies_rpm(self):
        self._mock_lsb("Fedora")
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:rpm"))
        self.assertIsInstance(depends.platform, Rpm)

    def test_ubuntu_implies_dpkg(self):
        self._mock_lsb("Ubuntu")
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
        mocker = mox.Mox()
        depends.platform = mocker.CreateMock(Platform)
        depends.platform.get_pkg_version("foo").AndReturn(None)
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.assertEqual(
            [('missing', ['foo'])], depends.check_rules([("foo", [], [])]))

    def test_check_rule_present(self):
        depends = Depends("")
        mocker = mox.Mox()
        depends.platform = mocker.CreateMock(Platform)
        depends.platform.get_pkg_version("foo").AndReturn("123")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.assertEqual([], depends.check_rules([("foo", [], [])]))

    def test_check_rule_incompatible(self):
        depends = Depends("")
        mocker = mox.Mox()
        depends.platform = mocker.CreateMock(Platform)
        depends.platform.get_pkg_version("foo").AndReturn("123")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.assertEqual(
            [('badversion', [('foo', "!=123", "123")])],
            depends.check_rules([("foo", [], [("!=", "123")])]))

    def test_parser_patterns(self):
        depends = Depends(dedent("""\
            foo
            bar [something]
            baz [platform:this platform:that-those]
            quux [anotherthing !nothing] <=12
            womp # and a comment
            # a standalone comment and a blank line

            # all's ok? good then
            """))
        self.assertEqual(len(depends.active_rules(['default'])), 2)

    def test_parser_invalid(self):
        self.assertRaises(ometa.runtime.ParseError,
                          lambda: Depends("foo [platform:bar@baz]\n"))


class TestDpkg(TestCase):

    def test_not_installed(self):
        platform = Dpkg()
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT).AndReturn(
                "foo deinstall ok config-files 4.0.0-0ubuntu1\n")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)
        self.assertEqual(None, platform.get_pkg_version("foo"))

    def test_unknown_package(self):
        platform = Dpkg()
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT).AndRaise(
                subprocess.CalledProcessError(
                    1, [], "dpkg-query: no packages found matching foo\n"))
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)
        self.assertEqual(None, platform.get_pkg_version("foo"))

    def test_installed_version(self):
        platform = Dpkg()
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["dpkg-query", "-W", "-f",
             "${Package} ${Status} ${Version}\n", "foo"],
            stderr=subprocess.STDOUT).AndReturn(
                "foo install ok installed 4.0.0-0ubuntu1\n")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)
        self.assertEqual("4.0.0-0ubuntu1", platform.get_pkg_version("foo"))


class TestRpm(TestCase):

    # NOTE: test_not_installed is not implemented as rpm seems to only be aware
    # of installed packages

    def test_unknown_package(self):
        platform = Rpm()
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["rpm", "--qf",
             "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n", "-q",
             "foo"],
            stderr=subprocess.STDOUT).AndRaise(
                subprocess.CalledProcessError(
                    1, [], "package foo is not installed\n"))
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)
        self.assertEqual(None, platform.get_pkg_version("foo"))

    def test_installed_version(self):
        platform = Rpm()
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["rpm", "--qf",
             "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n", "-q",
             "foo"],
            stderr=subprocess.STDOUT).AndReturn("foo 4.0.0-0.el6\n")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)
        self.assertEqual("4.0.0-0.el6", platform.get_pkg_version("foo"))


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
