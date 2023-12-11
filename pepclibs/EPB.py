# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>
#          Niklas Neronin <niklas.neronin@intel.com>
#
# Parts of the code was contributed by Len Brown <len.brown@intel.com>.

"""
This module provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
CPUs.
"""

import contextlib
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported, ErrorNotFound
from pepclibs.helperlibs import Trivial, ClassHelpers
from pepclibs import _EPBase

# EPB policy names, from the following Linux kernel file: arch/x86/kernel/cpu/intel_epb.c
_EPB_POLICIES = ("performance", "balance-performance", "normal", "balance-power", "power")

# The minimum and maximum EPB values.
_EPB_MIN, _EPB_MAX = 0, 15

class EPB(_EPBase.EPBase):
    """
    This class provides a capability of reading and changing EPB (Energy Performance Bias) on Intel
    CPUs.
    """

    def _get_epb_msr(self):
        """Returns an 'EnergyPerfBias.EnergyPerfBias()' object."""

        if not self._epb_msr:
            from pepclibs.msr import EnergyPerfBias # pylint: disable=import-outside-toplevel

            msr = self._get_msr()
            self._epb_msr = EnergyPerfBias.EnergyPerfBias(pman=self._pman, cpuinfo=self._cpuinfo,
                                                          msr=msr)
        return self._epb_msr

    def _validate_value(self, val, policy_ok=False):
        """
        Validate EPB value and raise appropriate exception. When 'policy_ok=True' also validate
        against accepted EPB policies.
        """

        # pylint: disable=unused-argument
        if Trivial.is_int(val):
            Trivial.validate_value_in_range(int(val), _EPB_MIN, _EPB_MAX, what="EPB value")
        elif not policy_ok:
            raise ErrorNotSupported(f"EPB value must be an integer within [{_EPB_MIN},{_EPB_MAX}]")
        elif val not in _EPB_POLICIES:
            policies = ", ".join(_EPB_POLICIES)
            raise ErrorNotSupported(f"EPB value must be one of the following EPB policies: "
                                    f"{policies}, or integer within [{_EPB_MIN},{_EPB_MAX}]")

    def _read_from_msr(self, cpu):
        """Read EPB for CPU 'cpu' from MSR."""

        try:
            return self._get_epb_msr().read_cpu_feature("epb", cpu)
        except ErrorNotSupported:
            return None

    def _write_to_msr(self, val, cpu):
        """Write EPB 'epb' for CPU 'cpu' to MSR."""

        _epb = self._get_epb_msr()

        try:
            _epb.write_cpu_feature("epb", val, cpu)
        except Error as err:
            raise type(err)(f"failed to set EPB HW{self._pman.hostmsg}:\n{err.indent(2)}") from err

    def _read_from_sysfs(self, cpu):
        """Read EPB for CPU 'cpu' from sysfs."""

        with contextlib.suppress(ErrorNotFound):
            return self._pcache.get("epb", cpu, "sysfs")

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r") as fobj:
                val = int(fobj.read().strip())
        except ErrorNotFound:
            val = None

        return self._pcache.add("epb", cpu, val, "sysfs")

    def _write_to_sysfs(self, val, cpu):
        """Write EPB 'epb' for CPU 'cpu' to sysfs."""

        self._pcache.remove("epb", cpu, "sysfs")

        try:
            with self._pman.open(self._sysfs_epb_path % cpu, "r+") as fobj:
                fobj.write(val)
        except Error as err:
            if isinstance(err, ErrorNotFound):
                err = ErrorNotSupported(err)
            raise type(err)(f"failed to set EPB{self._pman.hostmsg}:\n{err.indent(2)}") from err

        # Setting EPB to policy name will not read back the name, rather the numeric value.
        # E.g. "performance" EPB might be "0".
        if not Trivial.is_int(val):
            if not self._epb_policies[val]:
                self._epb_policies[val] = int(self._read_from_sysfs(cpu))

            self._pcache.add("epb", cpu, self._epb_policies[val], "sysfs")
        else:
            self._pcache.add("epb", cpu, int(val), "sysfs")

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPB for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        super().__init__("EPB", pman=pman, cpuinfo=cpuinfo, msr=msr, enable_cache=enable_cache)

        self._epb_msr = None

        # EPB scope is "CPU" on most platforms, but it may be something else of some platforms.
        try:
            self.sname = self._get_epb_msr().features["epb"]["sname"]
        except ErrorNotSupported:
            self.sname = "CPU"

        # EPB policy to EPB value dictionary.
        self._epb_policies = {name : None for name in _EPB_POLICIES}
        self._sysfs_epb_path = "/sys/devices/system/cpu/cpu%d/power/energy_perf_bias"

    def close(self):
        """Uninitialize the class object."""

        ClassHelpers.close(self, close_attrs=("_epb_msr",))
        super().close()
