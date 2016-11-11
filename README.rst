Introduction
============

Bindep is a tool for checking the presence of binary packages needed to
use an application / library. It started life as a way to make it easier to set
up a development environment for OpenStack projects. While OpenStack depends
heavily on `pip` for installation of Python dependencies, some dependencies are
not Python based, and particularly for testing, some dependencies have to be
installed before `pip` can be used - such as `virtualenv` and `pip` itself.

Basics
======

Create a file called ``bindep.txt`` and in that list any
requirements your application / library has. In your README or INSTALL or
other documentation you can tell users to run `bindep` to report on missing
dependencies. Users without `bindep` installed can consult the
``bindep.txt`` file by hand if they choose, or install `bindep`
first and then use it.

If no ``bindep.txt`` file exists, `bindep` will look at the
old location ``other-requirements.txt``.

The output from bindep is fairly verbose normally, but passing an option of
-b/--brief outputs just the missing packages one per line, suitable for feeding
to your package management tool of choice.

If you need to maintain multiple requirements list files you can pass a
specific filename with the -f/--file command line option. If you want to read
the list from standard input in a pipeline instead, use a filename of "-".

When bindep runs, its exit code is ``0`` if no described packages are missing,
but ``1`` if there are packages which it believes need to be installed.

Profiles
--------

Profiles can be used to describe different scenarios. For instance, you might
have a profile for using PostgreSQL which requires the PostgreSQL client
library, a profile for MySQL needing that client library, and a profile for
testing which requires both libraries as well as the servers. To select a
profile just pass it when running `bindep` - e.g.::

    $ bindep test

When running bindep a single profile can be chosen by the user, with no
explicit selection resulting in the selected profile being ``default``.
`bindep` will automatically activate additional profiles representing the
platform `bindep` is running under, making it easy to handle platform specific
quirks.

The available profiles are inferred by inspecting the requirements file
and collating the used profile names. Users can get a report on the 
available profiles::

    $ bindep --profiles


Writing Requirements Files
==========================

The requirements file ``bindep.txt`` lists the dependencies for
projects. Where non-ascii characters are needed, they should be UTF8 encoded.

The file is line orientated - each line is a Debian binary package name, an
optional profile selector and optional version constraints. (Note - if you are
writing an alternative parser, see the Debian policy manual for the parsing
rules for packagenames). Debian package names are used as a single source of
truth - `bindep` can be taught the mapping onto specific packaging systems.
Alternatively, profiles may be used to encode platform specific requirements.

Profiles are used to decide which lines in the requirements file should be
considered when checking dependencies. Profile selectors are a list of space
separated strings contained in ``[]``. A selector prefixed with ``!`` is a negative
selector. For a line in the requirements file to be active:

 * it must not have a negative selector that matches the active profile.
 * it must either have no positive selectors, or a positive selector that
   matches the active profile.

For instance, the profile selector ``[!qpid]`` will match every profile except
``qpid`` and would be suitable for disabling installation of rabbitmq when qpid
is in use. ``[default]`` would match only if the user has not selected a
profile (or selected ``default``). ``[default postgresql test]`` would match
those three profiles but not ``mysql``. ``[platform:rhel]`` will match only
when running in a RHEL linux environment.

Note that platform selectors are treated as kind of filter: If a line
contains a platform selector, then the package only gets installed if
at least one of the platform selectors matches in addition to the
match on the other selectors. As an example, ``[platform:rpm test]``
would only install a package on a RPM platform if the test selector is
used.

Version constraints are a comma separated list of constraints where each
constraint is  (== | < | <= | >= | > | !=) VERSION, and the constraints are ANDed
together (the same as pip requirements version constraints).

Comments are allowed: everything from the first ``#`` to the end of the line is
ignored.

Examples
--------

A simple example with using a test profile is::

    # A runtime dependency
    libffi6
    # A build time dependency
    libffi-devel [test]

bindep would select the ``libffi6`` package in all cases and if the
``test`` profile gets choosen with ``bindep test``, then both packages
would be selected.

The following content gives some examples as used in the `default bindep file
<http://git.openstack.org/cgit/openstack-infra/project-config/tree/jenkins/data/bindep-fallback.txt>`_
that OpenStack CI takes if no ``bindep.txt`` file exists for setup of
some jobs. The examples only use the automatically defined profiles
like ``platform:dpkg`` which is defined on Debian based systems.

If a repository needs for deployment the libxml2 development
libraries for support of Debian, Gentoo, and RPM based distros, the
``bindep.txt`` file can contain::

    libxml2-dev [platform:dpkg]
    libxml2-devel [platform:rpm]
    libxml2-utils [platform:dpkg]
    dev-libs/libxml2 [platform:gentoo]

This would select ``libxml2-dev`` and ``libxml2-utils`` packages on
Debian based distributions like Debian and Ubuntu since those entries
have the ``platform:dpkg`` profile, ``libxml2-devel`` on RPM based
distributions like CentOS, Fedora, openSUSE, Red Hat, or SUSE Linux
since those entries have the ``platform:rpm`` profile, and
``dev-libs/libxml2`` on Gentoo since the entry has the
``platform:gentoo`` profile.

To select Python3 development packages, the OpenStack CI default file uses::

    python3-all-dev [platform:dpkg !platform:ubuntu-precise]
    python3-devel [platform:fedora]
    python34-devel [platform:centos]

This selects ``python3-all-dev`` on all Debian based distributions
with the exception of Ubuntu Precise, ``python3-devel`` on Fedora and
``python34-devel`` on CentOS.

To select the curl package, the OpenStack CI default file uses::

    curl [!platform:gentoo]
    net-misc/curl [platform:gentoo]

This selects the ``curl`` package on all distributions with the
exception of Gentoo, and selects ``net-misc/curl`` on Gentoo only.
