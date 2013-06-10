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

grammar = """
rules = rule*
rule = <name>:name selector?:selector version?:version '\n' -> (
    name, selector or [], version or [])
lowercase = ('a'|'b'|'c'|'d'|'e'|'f'|'g'|'h'|'i'|'j'|'k'|'l'|'m'|'n'|'o'|'p'
            |'q'|'r'|'s'|'t'|'u'|'v'|'w'|'x'|'y'|'z')
name = (lowercase|digit):start (lowercase|digit|'.'|'+'|'-')+:rest
ws = ' '+
profile = ('!'?:neg <(lowercase|digit|':')+>:name) -> (neg!='!', name)
selector = ws '[' profile:p1 (ws profile)*:p2 ']' -> [p1] + p2
epoch = digit+ ':'
upstreamver = digit (letterOrDigit | '.' | '+' | '-' | '~' | ':')*
upstreamver_no_hyphen = digit (letterOrDigit | '.' | '+' | '~' | ':')*
debver = digit (letterOrDigit | '.' | '+' | '~')*
debversion = epoch? (upstreamver_no_hyphen | (upstreamver debver?))
oneversion = <('<=' | '<' | '!=' | '==' | '>=' | '>')>:rel <debversion>:v -> (
    rel, v)
version = ws oneversion:v1 (',' oneversion)*:v2 -> [v1] + v2
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
        return []

    def profiles(self):
        profiles = set()
        for rule in self._rules:
            for _, selector in rule[1]:
                profiles.add(selector)
        return sorted(profiles)

    def platform_profiles(self):
        distro = subprocess.check_output(
            ["lsb_release", "-si"], stderr=subprocess.STDOUT).strip().lower()
        atoms = set([distro])
        if distro in ["debian", "ubuntu"]:
            atoms.add("dpkg")
        return ["platform:%s" % (atom,) for atom in sorted(atoms)]
