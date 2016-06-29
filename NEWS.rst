Backward-Incompatible Changes Between 1.0.0 and 2.0.0
=====================================================

The following behavior changes between the 1.0.0 and 2.0.0 releases
break backward compatibility:

 * Running under Python 2.6 is no longer officially supported
 * If any platform profiles are listed for a package, at least one
   of them must match independently of whether any user profiles
   also match
