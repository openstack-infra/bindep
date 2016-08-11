Behavior Change in 2.1.0
========================

File bindep.txt is now the default bindep file. For compatibility with
previous releases, bindep will check other-requirements.txt if
bindep.txt does not exist. If both exist and the -f/--file option is
not specified, it will emit an error.

Backward-Incompatible Changes Between 1.0.0 and 2.0.0
=====================================================

The following behavior changes between the 1.0.0 and 2.0.0 releases
break backward compatibility:

 * Running under Python 2.6 is no longer officially supported
 * If any platform profiles are listed for a package, at least one
   of them must match independently of whether any user profiles
   also match
