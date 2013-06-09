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

import logging
import optparse
import sys


def main(depfactory=None):
    if depfactory is None:
        try:
            open('other-requirements.txt', 'rt')
        except IOError:
            logging.error('No other-requirements.txt file found.')
            return 1
    else:
        depends = depfactory()
    parser = optparse.OptionParser()
    parser.add_option("--profiles", action="store_true",
        help="List the platform and configuration profiles.")
    opts, args = parser.parse_args()
    if opts.profiles:
        logging.info("Platform profiles:")
        for profile in depends.platform_profiles():
            logging.info("%s", profile)
        logging.info("")
        logging.info("Configuration profiles:")
        for profile in depends.profiles():
            logging.info("%s", profile)
    return 0


if __name__ == '__main__':
    sys.exit(main())
