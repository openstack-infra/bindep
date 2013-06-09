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


class Depends(object):
    """Project dependencies."""

    def __init__(self, depends_string):
        """Construct a Depends instance.

        :param depends_string: The string description of the requirements that
            need to be satisfied. See the bindep README.rst for syntax for the
            requirements list.
        """

    def profiles(self):
        return []

    def platform_profiles(self):
        distro = subprocess.check_output(
            ["lsb_release", "-si"], stderr=subprocess.STDOUT).strip().lower()
        atoms = set([distro])
        if distro in ["debian", "ubuntu"]:
            atoms.add("dpkg")
        return ["platform:%s" % (atom,) for atom in sorted(atoms)]
