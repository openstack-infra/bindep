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

import mox
from testtools.matchers import Contains
from testtools import TestCase

from bindep.depends import Depends


class TestDepends(TestCase):

    def test_empty_file(self):
        depends = Depends("")
        self.assertEqual([], depends.profiles())

    def test_platform_profiles_succeeds(self):
        depends = Depends("")
        self.assertIsInstance(depends.platform_profiles(), list)

    def _mock_lsb(self):
        mocker = mox.Mox()
        mocker.StubOutWithMock(subprocess, "check_output")
        subprocess.check_output(
            ["lsb_release", "-si"],
            stderr=subprocess.STDOUT).AndReturn("Ubuntu\n")
        mocker.ReplayAll()
        self.addCleanup(mocker.VerifyAll)
        self.addCleanup(mocker.UnsetStubs)

    def test_detects_ubuntu(self):
        self._mock_lsb()
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:ubuntu"))

    def test_ubuntu_implies_dpkg(self):
        self._mock_lsb()
        depends = Depends("")
        self.assertThat(
            depends.platform_profiles(), Contains("platform:dpkg"))
