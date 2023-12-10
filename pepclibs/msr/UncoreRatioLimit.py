# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x620 (MSR_UNCORE_RATIO_LIMIT). This MSR provides a way to limit
uncore frequency on Intel platforms.
"""

from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

# The Uncore Ratio Limit Model Specific Register.
MSR_UNCORE_RATIO_LIMIT = 0x620

#
# CPU models that support the uncore ratio limit MSR.
#
_CPUS = CPUInfo.EMRS +                            \
        CPUInfo.METEORLAKES +                     \
        CPUInfo.SPRS +                            \
        CPUInfo.RAPTORLAKES +                     \
        (CPUInfo.CPUS["ALDERLAKE"]["model"],      \
         CPUInfo.CPUS["ALDERLAKE_L"]["model"],) + \
        CPUInfo.ICXES +                           \
        CPUInfo.SKXES +                           \
        (CPUInfo.CPUS["BROADWELL_G"]["model"],    \
         CPUInfo.CPUS["BROADWELL_D"]["model"],    \
         CPUInfo.CPUS["BROADWELL_X"]["model"],)

# Description of CPU features controlled by the the Turbo Ratio Limit MSR. Please, refer to the
# notes for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "max_ratio" : {
        "name" : "Maximum uncore ratio",
        "sname": None,
        "help" : """The maximum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                    the maximum allowed uncore frequency.""",
        "cpumodels" : _CPUS,
        "type"      : "int",
        "writable"  : True,
        "bits"      : (6, 0),
    },
    "min_ratio" : {
        "name" : "Minimum uncore ratio",
        "sname": None,
        "help" : """The minimum allowed uncore ratio. This ratio multiplied by bus clock speed gives
                    the minimum allowed uncore frequency.""",
        "cpumodels" : _CPUS,
        "type"      : "int",
        "writable"  : True,
        "bits"      : (14, 8),
    },
}

class UncoreRatioLimit(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x620 (MSR_UNCORE_RATIO_LIMIT). This MSR provides a way to limit
    uncore frequency on Intel platforms.
    """

    regaddr = MSR_UNCORE_RATIO_LIMIT
    regname = "MSR_UNCORE_RATIO_LIMIT"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES

        sname = self._get_clx_ap_adjusted_msr_scope()
        for finfo in self.features.values():
            finfo["sname"] = sname

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
