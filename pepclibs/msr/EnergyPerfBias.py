# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1B1 (MSR_ENERGY_PERF_BIAS). This is an architectural MSR found on
many Intel platforms.
"""

from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR

# The Energy Performance Bias Model Specific Register.
MSR_ENERGY_PERF_BIAS = 0x1B0

# MSR_ENERGY_PERF_BIAS features have CPU scope, except for the following CPU models.
_CORE_SCOPE_CPUS = CPUInfo.SILVERMONTS
_PACKAGE_SCOPE_CPUS = CPUInfo.WESTMERES + CPUInfo.SANDYBRIDGES

# Description of CPU features controlled by the the Power Control MSR. Please, refer to the notes
# for '_FeaturedMSR.FEATURES' for more comments.
FEATURES = {
    "epb": {
        "name": "Energy Performance Bias",
        "sname": None,
        "iosname": None,
        "help": """Energy Performance Bias is a hint to the CPU about the power and performance
                   preference. Value 0 indicates highest performance and value 15 indicates
                   maximum energy savings.""",
        "cpuflags": {"epb",},
        "type": "int",
        "bits": (3, 0),
    },
}

class EnergyPerfBias(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1B1 (MSR_ENERGY_PERF_BIAS). This is an architectural MSR found
    on many Intel platforms.
    """

    regaddr = MSR_ENERGY_PERF_BIAS
    regname = "MSR_ENERGY_PERF_BIAS"
    vendor = "GenuineIntel"

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        model = self._cpuinfo.info["model"]

        if model in _CORE_SCOPE_CPUS:
            sname = "core"
        elif model in _PACKAGE_SCOPE_CPUS:
            sname = "package"
        else:
            sname = "CPU"

        for finfo in self.features.values():
            finfo["sname"] = finfo["iosname"] = sname

    def __init__(self, pman=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(pman=pman, cpuinfo=cpuinfo, msr=msr)
