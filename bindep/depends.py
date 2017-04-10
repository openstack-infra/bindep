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
import subprocess
import sys


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
profile = ('!'?:neg <(lowercase|digit|':'|'-')+>:name) -> (neg!='!', name)
selector = ws '[' profile:p1 (ws profile)*:p2 ']' -> [p1] + p2
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
        for sense, profile in rule[1]:
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
        negative = False
        for sense, profile in partition_rule:
            if sense:
                positive = True
                if profile in profiles:
                    match_found = True
            else:
                if profile in profiles:
                    negative = True
                    break
        if not negative and (match_found or not positive):
                return True
        return False

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

    def platform_profiles(self):
        output = subprocess.check_output(
            ["lsb_release", "-cirs"],
            stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        lsbinfo = output.lower().split()
        # NOTE(toabctl): distro can be more than one string (i.e. "SUSE LINUX")
        codename = lsbinfo[len(lsbinfo) - 1:len(lsbinfo)][0]
        release = lsbinfo[len(lsbinfo) - 2:len(lsbinfo) - 1][0]
        # NOTE(toabctl): space is a delimiter for bindep, so remove the spaces
        distro = "".join(lsbinfo[0:len(lsbinfo) - 2])
        atoms = set([distro])
        atoms.add("%s-%s" % (distro, codename))
        releasebits = release.split(".")
        for i in range(len(releasebits)):
            atoms.add("%s-%s" % (distro, ".".join(releasebits[:i + 1])))
        if distro in ["debian", "ubuntu"]:
            atoms.add("dpkg")
            self.platform = Dpkg()
        elif distro in ["centos", "redhatenterpriseserver", "fedora",
                        "opensuse", "suselinux"]:
            if distro == "redhatenterpriseserver":
                # just short alias
                atoms.add("rhel")
            atoms.add("rpm")
            self.platform = Rpm()
        elif distro in ["gentoo"]:
            atoms.add("emerge")
            self.platform = Emerge()
        elif distro in ["arch"]:
            atoms.add("pacman")
            self.platform = Pacman()
        return ["platform:%s" % (atom,) for atom in sorted(atoms)]


class Platform(object):
    """Interface for querying platform specific info."""

    def get_pkg_version(self, pkg_name):
        """Find the installed version of pkg_name.

        :return: None if pkg_name is not installed, or a version otherwise.
        """
        raise NotImplementedError(self.get_pkg_version)


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
                 "%{NAME} %|EPOCH?{%{EPOCH}:}|%{VERSION}-%{RELEASE}\n", "-q",
                 pkg_name],
                stderr=subprocess.STDOUT).decode(getpreferredencoding(False))
        except subprocess.CalledProcessError as e:
            eoutput = e.output.decode(getpreferredencoding(False))
            if (e.returncode == 1 and
                eoutput.strip().endswith('is not installed')):
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
