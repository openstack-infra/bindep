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

from parsley import makeGrammar
import subprocess

if not getattr(subprocess, 'check_output', None):
    import bindep.support_py26
    # shut pyflakes up.
    bindep.support_py26


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
name = letterOrDigit:start (letterOrDigit|'.'|'+'|'-')+:rest
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


class Depends(object):
    """Project dependencies."""

    def __init__(self, depends_string):
        """Construct a Depends instance.

        :param depends_string: The string description of the requirements that
            need to be satisfied. See the bindep README.rst for syntax for the
            requirements list.
        """
        parser = makeGrammar(grammar, {})(depends_string)
        self._rules = parser.rules()

    def active_rules(self, profiles):
        """Return the rules active given profiles.

        :param profiles: A list of profiles to consider active. This should
            include platform profiles - they are not automatically included.
        """
        profiles = set(profiles)
        result = []
        for rule in self._rules:
            # Have we seen any positive selectors - if not, the absence of
            # negatives means we include the rule, but if we any positive
            # selectors we need a match.
            positive = False
            match_found = False
            negative = False
            for sense, profile in rule[1]:
                if sense:
                    positive = True
                    if profile in profiles:
                        match_found = True
                else:
                    if profile in profiles:
                        negative = True
                        break
            if not negative and (match_found or not positive):
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
        distro, release, codename = subprocess.check_output(
            ["lsb_release", "-cirs"], stderr=subprocess.STDOUT).lower().split()
        atoms = set([distro])
        atoms.add("%s-%s" % (distro, codename))
        releasebits = release.split(".")
        for i in range(len(releasebits)):
            atoms.add("%s-%s" % (distro, ".".join(releasebits[:i + 1])))
        if distro in ["debian", "ubuntu"]:
            atoms.add("dpkg")
            self.platform = Dpkg()
        elif distro in ["centos", "fedora"]:
            atoms.add("rpm")
            self.platform = Rpm()
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
                 pkg_name], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            if (e.returncode == 1 and
                (e.output.startswith('dpkg-query: no packages found') or
                 e.output.startswith('No packages found matching'))):
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
                 pkg_name], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            if (e.returncode == 1 and
                e.output.strip().endswith('is not installed')):
                return None
            raise
        # output looks like
        # name version
        output = output.strip()
        elements = output.split(' ')
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
