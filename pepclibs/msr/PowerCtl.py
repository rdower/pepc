# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides API to MSR 0x1FC (MSR_POWER_CTL). This is a model-specific register found on
many Intel platforms.
"""

import logging
from pepclibs import CPUInfo
from pepclibs.msr import _FeaturedMSR
from pepclibs.helperlibs.Exceptions import ErrorNotSupported

_LOG = logging.getLogger()

# The Power Control Model Specific Register.
MSR_POWER_CTL = 0x1FC

# Description of CPU features controlled by the the Power Control MSR.
#
# Note 1: this is only the initial, general definition. Some things are platform-dependent, so full
#          dictionary is available in 'PCStateConfigCtl.features'.
# Note 2: while the "C-state prewake" feature available on many CPUs, in practice it works only on
#         on some platforms, like Ice Lake Xeon. Therefore we mark it as "supported" only for those
#         platforms where we know it works.
FEATURES = {
    "c1e_autopromote" : {
        "name" : "C1E autopromote",
        "scope": "package",
        "help" : f"""When enabled, the CPU automatically converts all C1 requests to C1E requests.
                     This CPU feature is controlled by MSR {MSR_POWER_CTL:#x}, bit 1.""",
        "type" : "bool",
        "vals" : { "enabled" : 1, "disabled" : 0},
        "bits" : (1, 1),
    },
    "cstate_prewake" : {
        "name" : "C-state prewake",
        "scope": "package",
        "help" : f"""When enabled, the CPU will start exiting the C6 idle state in advance, prior to
                     the next local APIC timer event. This CPU feature is controlled by MSR
                     {MSR_POWER_CTL:#x}, bit 30.""",
        "cpumodels" : (CPUInfo.INTEL_FAM6_IVYBRIDGE_X, CPUInfo.INTEL_FAM6_ICELAKE_X,
                       CPUInfo.INTEL_FAM6_ICELAKE_D),
        "type" : "bool",
        "vals" : { "enabled" : 0, "disabled" : 1},
        "bits" : (30, 30),
    },
}

class PowerCtl(_FeaturedMSR.FeaturedMSR):
    """
    This class provides API to MSR 0x1FC (MSR_POWER_CTL). This is a model-specific register found on
    many Intel platforms.
    """

    def _set_baseclass_attributes(self):
        """Set the attributes the superclass requires."""

        self.features = FEATURES
        self.regaddr = MSR_POWER_CTL
        self.regname = "MSR_POWER_CTL"

    def __init__(self, proc=None, cpuinfo=None, msr=None):
        """
        The class constructor. The argument are as follows.
          * proc - the 'Proc' or 'SSH' object that defines the host to run the measurements on.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - the 'MSR.MSR()' object to use for writing to the MSR register.
        """

        super().__init__(proc=proc, cpuinfo=cpuinfo, msr=msr)
