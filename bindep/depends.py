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

from locale import getpreferredencoding
import logging
import os.path
from parsley import makeGrammar
import platform
import subprocess
import sys

import distro


debversion_grammar = """
epoch = <digit+>:d ':' -> d
trailingdeb = (upstream_segment* '-' debver)
upstream_segment = (letterOrDigit | '.' | '+' | '~' | ':')
upstreamver = digit (upstream_segment | ('-' ~~trailingdeb))*
upstreamver_no_hyphen = digit (letterOrDigit | '.' | '+' | '~' | ':')*
debver = (letterOrDigit | '.' | '+' | '~')+
upstream_no_hyphen = epoch?:e <upstreamver_no_hyphen>:u -> (e or '0', u, "")
upstream_hyphen = epoch?:e <upstreamver>:u '-' <debver>:d -> (e or '0', u, d)
debversion = upstream_hyphen | upstream_no_hyphen
"""

debversion_compiled = makeGrammar(debversion_grammar, {})


grammar = debversion_grammar + """
rules = (rule|comment|blank)*:bits -> [r for r in bits if r is not None]
rule = <name>:name selector?:selector version?:version ('\n'|comment) -> (
    name, selector or [], version or [])
lowercase = ('a'|'b'|'c'|'d'|'e'|'f'|'g'|'h'|'i'|'j'|'k'|'l'|'m'|'n'|'o'|'p'
            |'q'|'r'|'s'|'t'|'u'|'v'|'w'|'x'|'y'|'z')
name = letterOrDigit:start (letterOrDigit|'.'|'+'|'-'|'_'|'/')+:rest
ws = ' '+
profile = ('!'?:neg <(lowercase|digit|':'|'-'|'.')+>:name) -> (neg!='!', name)
profiles = '(' (ws? profile)*:p ws? ')' -> p
group = profiles | profile
selector = ws '[' (ws? group)*:p ws? ']' -> p
oneversion = <('<=' | '<' | '!=' | '==' | '>=' | '>')>:rel <debversion>:v -> (
    rel, v)
version = ws oneversion:v1 (',' oneversion)*:v2 -> [v1] + v2
comment = ws? '#' any* '\n' -> None
any = ~'\n' anything
blank = ws? '\n' -> None
"""


def get_depends(filename=None):
    fd = get_depends_file(filename)
    if not fd:
        return None
    return Depends(fd.read())


def get_depends_file(filename=None):
    log = logging.getLogger(__name__)
    if filename == "-":
        return sys.stdin
    elif filename:
        try:
            fd = open(filename, 'rt')
        except IOError:
            log.error('Error reading file %s.' % filename)
            return None
    else:
        if (os.path.isfile('bindep.txt') and
            os.path.isfile('other-requirements.txt')):
            log.error(
                'Both bindep.txt and other-requirements.txt '
                'files exist, choose one.')
            return None
        if os.path.isfile('bindep.txt'):
            try:
                fd = open('bindep.txt', 'rt')
            except IOError:
                log.error('Error reading file bindep.txt.')
                return None
        elif os.path.isfile('other-requirements.txt'):
            try:
                fd = open('other-requirements.txt', 'rt')
            except IOError:
                log.error('Error reading file other-requirements.txt.')
                return None
        else:
            log.error(
                'Neither file bindep.txt nor file '
                'other-requirements.txt exist.')
            return None
    return fd


class Depends(object):
    """Project dependencies."""

    # Truth table for combining platform and user profiles:
    # (platform, user) where False means that component
    # voted definitely no, True means that that component
    # voted definitely yes and None means that that component
    # hasn't voted.
    _include = {
        (False, False): False,
        (False, None): False,
        (False, True): False,
        (None, False): False,
        (None, None): True,
        (None, True): True,
        (True, False): False,
        (True, None): True,
        (True, True): True,
    }

    def __init__(self, depends_string):
        """Construct a Depends instance.

        :param depends_string: The string description of the requirements that
            need to be satisfied. See the bindep README.rst for syntax for the
            requirements list.
        """
        parser = makeGrammar(grammar, {})(depends_string)
        self._rules = parser.rules()

    def _partition(self, rule):
        """Separate conditions into platform and user profiles.

        :return Two lists, the platform and user profiles.
        """
        platform = []
        user = []
        for group in rule[1]:
            if isinstance(group, list):
                user.append(group)
                continue
            sense, profile = group
            if profile.startswith("platform:"):
                platform.append((sense, profile))
            else:
                user.append((sense, profile))
        return platform, user

    def _evaluate(self, partition_rule, profiles):
        """Evaluate rule. Does it match the profiles?

        :return Result is trinary: False for definitely no, True for
        definitely yes, None for no rules present.
        """
        if partition_rule == []:
            return None

        # Have we seen any positive selectors - if not, the absence of
        # negatives means we include the rule, but if we any positive
        # selectors we need a match.
        positive = False
        match_found = False
        group_found = False
        group_match_found = False
        negative = False
        for group in partition_rule:
            if isinstance(group, list):
                group_found = True
                if self._match_all(group, profiles):
                    group_match_found = True
                continue
            sense, profile = group
            if sense:
                positive = True
                if profile in profiles:
                    match_found = True
            else:
                if profile in profiles:
                    negative = True
                    break
        if not negative:
            if group_match_found or match_found:
                return True
            if not group_found and not positive:
                return True
        return False

    def _match_all(self, partition_rules, profiles):
        """Evaluate rules. Do they all match the profiles?

        :return Result True if all profiles match else False
        """
        def matches(sense, profile, profiles):
            return sense if profile in profiles else not sense

        for sense, profile in partition_rules:
            if not matches(sense, profile, profiles):
                return False
        return True

    def active_rules(self, profiles):
        """Return the rules active given profiles.

        :param profiles: A list of profiles to consider active. This should
            include platform profiles - they are not automatically included.
        """
        profiles = set(profiles)
        result = []
        for rule in self._rules:
            # Partition rules
            platform_profiles, user_profiles = self._partition(rule)
            # Evaluate each partition separately
            platform_status = self._evaluate(platform_profiles, profiles)
            user_status = self._evaluate(user_profiles, profiles)
            # Combine results
            # These are trinary: False for definitely no, True for
            # definitely yes, None for no rules present.
            if self._include[platform_status, user_status]:
                result.append(rule)
        return result

    def list_all_packages(self, rules, output_format='newline'):
        """Print a list of all packages that are required on this platform
        according to the passed in rules. This is useful if we want to build
        RPMs based on the deps listed in bindeps.txt

        :param rules: A list of rules, as returned by active_rules.
        :param output_format: The format to print the output in. Currently
        we support newline format which will print 1 package per line, and
        csv format which prints a csv list.
        :return: List of all required packages regardless of whether they are
        missing.
        """
        packages_list = [rule[0] for rule in rules]
        if output_format == 'csv':
            logging.info(','.join(packages_list))
        elif output_format == 'newline':
            logging.info('\n'.join(packages_list))
        return packages_list

    def check_rules(self, rules):
        """Evaluate rules against the local environment.

        :param rules: A list of rules, as returned by active_rules.
        :return: A list of unsatisfied rules.
        """
        missing = set()
        incompatible = []
        for rule in rules:
            installed = self.platform.get_pkg_version(rule[0])
            if not installed:
                missing.add(rule[0])
                continue
            for operator, constraint in rule[2]:
                if not _eval(installed, operator, constraint):
                    incompatible.append(
                        (rule[0], '%s%s' % (operator, constraint), installed))
        result = []
        if missing:
            result.append(("missing", sorted(missing)))
        if incompatible:
            result.append(("badversion", incompatible))
        return result

    def profiles(self):
        profiles = set()
        for rule in self._rules:
            for _, selector in rule[1]:
                profiles.add(selector)
        return sorted(profiles)

    def codenamebits(self, distro_id, codename):
        atoms = set()
        codenamebits = codename.split()
        for i in range(len(codenamebits)):
            atoms.add("%s-%s" % (distro_id, "-".join(codenamebits[:i + 1])))
        return atoms

    def releasebits(self, distro_id, release):
        atoms = set()
        releasebits = release.split(".")
        for i in range(len(releasebits)):
            atoms.add("%s-%s" % (distro_id, ".".join(releasebits[:i + 1])))
        return atoms

    def platform_profiles(self):
        if platform.system() == 'Darwin':
            atoms = set(['darwin'])
            # detect available macos package managers
            if os.system('which brew >/dev/null') == 0:
                atoms.add('brew')
                self.platform = Brew()
            return ["platform:%s" % (atom,) for atom in sorted(atoms)]
        distro_id = distro.id()
        if not distro_id:
            log = logging.getLogger(__name__)
            log.error('Unable to determine distro ID. '
                      'Does /etc/os-release exist or '
                      'is lsb_release installed?')
            raise Exception('Distro name not found')
        # NOTE(toabctl): distro can be more than one string (i.e. "SUSE LINUX")
        codename = distro.codename().lower()
        release = distro.version().lower()
        # NOTE(toabctl): space is a delimiter for bindep, so remove the spaces
        distro_id = "".join(distro_id.split()).lower()
        atoms = set([distro_id])
        atoms.update(self.codenamebits(distro_id, codename))
        atoms.update(self.releasebits(distro_id, release))
        if distro_id in ["debian", "ubuntu"]:
            atoms.add("dpkg")
            self.platform = Dpkg()
        # RPM distros seem to be especially complicated
        elif distro_id in ["amzn", "amazonami",
                           "centos", "rhel",
                           "redhatenterpriseserver",
                           "redhatenterpriseworkstation",
                           "fedora",
                           "opensuseproject", "opensuse",
                           "opensuse-tumbleweed", "sles", "suselinux"]:
            # Distro aliases
            if distro_id in ["redhatenterpriseserver",
                             "redhatenterpriseworkstation"]:
                # just short alias
                atoms.add("rhel")
                atoms.update(self.codenamebits("rhel", codename))
                atoms.update(self.releasebits("rhel", release))
            elif distro_id == 'rhel' and 'server' in distro.name().lower():
                atoms.add("redhatenterpriseserver")
                atoms.update(self.codenamebits("redhatenterpriseserver",
                                               codename))
                atoms.update(self.releasebits("redhatenterpriseserver",
                                              release))
            elif (distro_id == 'rhel' and
                    'workstation' in distro.name().lower()):
                atoms.add("redhatenterpriseworkstation")
                atoms.update(self.codenamebits("redhatenterpriseworkstation",
                                               codename))
                atoms.update(self.releasebits("redhatenterpriseworkstation",
                                              release))
            elif "amzn" in distro_id:
                atoms.add("amazonami")
                atoms.update(self.codenamebits("amazonami", codename))
                atoms.update(self.releasebits("amazonami", release))
            elif "amazonami" in distro_id:
                atoms.add("amzn")
                atoms.update(self.codenamebits("amzn", codename))
                atoms.update(self.releasebits("amzn", release))
            elif "opensuse" in distro_id:
                # just short alias
                atoms.add("opensuse")
                atoms.update(self.codenamebits("opensuse", codename))
                atoms.update(self.releasebits("opensuse", release))
                atoms.add("opensuseproject")
                atoms.update(self.codenamebits("opensuseproject", codename))
                atoms.update(self.releasebits("opensuseproject", release))
            elif "sles" in distro_id:
                atoms.add("suselinux")
                atoms.update(self.codenamebits("suselinux", codename))
                atoms.update(self.releasebits("suselinux", release))
            elif "suselinux" in distro_id:
                atoms.add("sles")
                atoms.update(self.codenamebits("sles", codename))
                atoms.update(self.releasebits("sles", release))

            # Family aliases
            if 'suse' in distro_id or distro_id == 'sles':
                atoms.add("suse")
            else:
                atoms.add("redhat")

            atoms.add("rpm")
            self.platform = Rpm()
        elif distro_id in ["gentoo"]:
            atoms.add("emerge")
            self.platform = Emerge()
        elif distro_id in ["arch"]:
            atoms.add("pacman")
            self.platform = Pacman()
        else:
            self.platform = Unknown()
        return ["platform:%s" % (atom,) for atom in sorted(atoms)]


class Platform(object):
    """Interface for querying platform specific info."""

    def get_pkg_version(self, pkg_name):
        """Find the installed version of pkg_name.

        :return: None if pkg_name is not installed, or a version otherwise.
        """
        raise NotImplementedError(self.get_pkg_version)


class Unknown(Platform):
    """Unknown platform implementation. Raises error."""

    def get_pkg_version(self, pkg_name):
        raise Exception("Uknown package manager for current platform.")


class Brew(Platform):
    """brew specific platform implementation."""

    def get_pkg_version(self, pkg_name):
        try:
            output = subprocess.check_output(
                ['brew', 'list', '--versions',
                 pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            if (e.returncode == 1):
                return None
            raise
        # output looks like
        # git 2.15.1_1 2.15.0
        output = output.strip()
        elements = output.split(' ')[1:]
        # brew supports multiple versions, we will only return the first one
        return elements[0]


class Dpkg(Platform):
    """dpkg specific platform implementation.

    This currently shells out to dpkg, it could in future use python-apt.
    """

    def get_pkg_version(self, pkg_name):
        try:
            output = subprocess.check_output(
                ["dpkg-query", "-W", "-f", "${Package} ${Status} ${Version}\n",
                 pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            eoutput = e.output.decode(getpreferredencoding(False))
            if (e.returncode == 1 and
                (eoutput.startswith('dpkg-query: no packages found') or
                 eoutput.startswith('No packages found matching'))):
                return None
            raise
        # output looks like
        # name planned status install-status version
        output = output.strip()
        elements = output.split(' ')
        if elements[3] != 'installed':
            return None
        return elements[4]


class Rpm(Platform):
    """rpm specific platform implementation.

    This currently shells out to rpm, it could in future use rpm-python if
    that ever gets uploaded to PyPI.
    """

    def get_pkg_version(self, pkg_name):
        try:
            output = subprocess.check_output(
                ["rpm", "--qf",
                 "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n",
                 "--whatprovides", "-q", pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            eoutput = e.output.decode(getpreferredencoding(False))
            if (e.returncode == 1 and
                (eoutput.strip().endswith('is not installed') or
                 (eoutput.strip().startswith('no package provides')))):
                return None
            raise
        # output looks like
        # name version
        output = output.strip()
        elements = output.split(' ')
        return elements[1]


class Emerge(Platform):
    """emerge specific implementation.

    This currently shells out to equery, it could be changed to eix to be
    faster but that would add another dependency and eix's cache would need to
    be updated before this is run.
    """

    def get_pkg_version(self, pkg_name):
        try:
            output = subprocess.check_output(
                ['equery', 'l', '--format=\'$version\'', pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            if e.returncode == 3:
                return None
            raise
        # output looks like
        # version
        output = output.strip()
        elements = output.split(' ')
        return elements[0]


class Pacman(Platform):
    """pacman specific implementation.

    This shells out to pacman
    """

    def get_pkg_version(self, pkg_name):
        try:
            output = subprocess.check_output(
                ['pacman', '-Q', pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            eoutput = e.output.decode(getpreferredencoding(False))
            if e.returncode == 1 and eoutput.endswith('was not found'):
                return None
            raise
        # output looks like
        # version
        elements = output.strip().split(' ')
        return elements[1]


def _eval_diff(operator, diff):
    """Return the boolean result for operator given diff.

    :param diff: An int with negative values meaning the right most parameter
        to the _eval function was greater than the left most parameter.
    :return: True if the operator was satisfied.
    """
    if operator == "==":
        return diff == 0
    if operator == "!=":
        return diff != 0
    if operator == "<":
        return diff < 0
    if operator == "<=":
        return diff <= 0
    if operator == ">":
        return diff > 0
    if operator == ">=":
        return diff >= 0


def _to_ord(character):
    # Per http://www.debian.org/doc/debian-policy/ch-controlfields.html
    # The lexical comparison is a comparison of ASCII values modified so that
    # all the letters sort earlier than all the non-letters and so that a
    # tilde sorts before anything, even the end of a part.
    # ord(~) -> 126
    # ord('A') -> 65
    # ord('Z') -> 90
    # ord('a') -> 97
    # ord('z') -> 122
    # ord('+') -> 43
    # ord('-') -> 45
    # ord('.') -> 46
    # ord(':') -> 58
    if not character or character.isdigit():  # end of a part
        return 1
    elif character == '~':
        return 0
    else:
        ordinal = ord(character)
        if ordinal < 65:
            # Shift non-characters up beyond the highest character.
            ordinal += 100
        return ordinal


def _cmp_nondigit(left, right):
    l_ord = _to_ord(left)
    r_ord = _to_ord(right)
    return l_ord - r_ord


def _find_int(a_str, offset):
    """Find an int within a_str.

    :return: The int and the offset of the first character after the int.
    """
    if offset == len(a_str):
        return 0, offset
    initial_offset = offset
    while offset < len(a_str):
        offset += 1
        try:
            int(a_str[initial_offset:offset])
        except ValueError:
            # past the end of the decimal bit
            offset -= 1
            break
    return int(a_str[initial_offset:offset]), offset


def _eval(installed, operator, constraint):
    if operator == "==":
        return installed == constraint
    if operator == "!=":
        return installed != constraint
    constraint_parsed = debversion_compiled(constraint).debversion()
    installed_parsed = debversion_compiled(installed).debversion()
    diff = int(installed_parsed[0]) - int(constraint_parsed[0])
    if diff:
        return _eval_diff(operator, diff)
    diff = _cmp_segment(installed_parsed[1], constraint_parsed[1])
    if diff:
        return _eval_diff(operator, diff)
    diff = _cmp_segment(installed_parsed[2], constraint_parsed[2])
    return _eval_diff(operator, diff)


def _cmp_segment(l_str, r_str):
    r_offset = 0
    l_offset = 0
    while (r_offset < len(r_str)) or (l_offset < len(l_str)):
        r_char = r_str[r_offset:r_offset + 1]
        l_char = l_str[l_offset:l_offset + 1]
        if ((not r_char or r_char.isdigit())
            and (not l_char or l_char.isdigit())):
            l_int, l_offset = _find_int(l_str, l_offset)
            r_int, r_offset = _find_int(r_str, r_offset)
            diff = l_int - r_int
            if diff:
                return diff
        diff = _cmp_nondigit(l_char, r_char)
        if diff:
            return diff
        if not l_char.isdigit() and l_offset < len(l_str):
            l_offset += 1
        if not r_char.isdigit() and r_offset < len(r_str):
            r_offset += 1
    return 0
