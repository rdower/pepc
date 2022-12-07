# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@linux.intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a capability of reading and changing EPP (Energy Performance Preference) on
Intel CPUs.
"""

from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound, ErrorNotSupported
from pepclibs.helperlibs import LocalProcessManager, Trivial, ClassHelpers
from pepclibs import CPUInfo, _PropsCache
from pepclibs.msr import MSR, HWPRequest, HWPRequestPkg

# The fall-back EPP policy to EPP value map.
#
# Note, we do not expose the values to the user because they are platform-specific (even though in
# current implementation they are not, but we can improve this later).
_EPP_POLICIES = {"performance": 0,
                 "balance_performance": 0x80,
                 "balance_power": 0xC0,
                 "power": 0xFF}

# The minimum and maximum EPP values.
_EPP_MIN, _EPP_MAX = 0, 0xFF

class EPP(ClassHelpers.SimpleCloseContext):
    """
    This module provides a capability of reading and changing EPP (Energy Performance Preference) on
    Intel CPUs.

    Public methods overview.

    1. Multiple CPUs.
        * Get EPP through MSR: 'get_epp()'.
        * Set EPP through MSR or sysfs: 'set_epp()'.
        * Get EPP policy name through MSR or sysfs: 'get_epp_policy()'.
        * Get the list of available EPP policies through sysfs: 'get_epp_policies()'.
    2. Single CPU.
        * Get EPP through MSR: 'get_cpu_epp()'.
        * Set EPP through MSR or sysfs: 'set_cpu_epp()'.
        * Get EPP policy name through MSR or sysfs: 'get_cpu_epp_policy()'.
        * Get the list of available EPP policies through sysfs: 'get_cpu_epp_policies()'.
        * Check if the CPU supports EPP via sysfs or MSR: 'is_epp_supported()'
    """

    def _get_msr(self):
        """Returns an 'MSR.MSR()' object."""

        if not self._msr:
            self._msr = MSR.MSR(self._pman, cpuinfo=self._cpuinfo, enable_cache=self._enable_cache)
        return self._msr

    def _get_hwpreq(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq:
            msr = self._get_msr()
            self._hwpreq = HWPRequest.HWPRequest(pman=self._pman, cpuinfo=self._cpuinfo, msr=msr)

        return self._hwpreq

    def _get_hwpreq_pkg(self):
        """Returns an 'HWPRequest.HWPRequest()' object."""

        if not self._hwpreq_pkg:
            msr = self._get_msr()
            self._hwpreq_pkg = HWPRequestPkg.HWPRequestPkg(pman=self._pman, cpuinfo=self._cpuinfo,
                                                           msr=msr)
        return self._hwpreq_pkg

    def is_epp_supported(self, cpu):
        """Returns 'True' if EPP is supported, on CPU 'cpu', otherwise returns 'False'."""

        if self._pcache.is_cached("supported", cpu):
            return self._pcache.get("supported", cpu)

        if self._pman.exists(self._sysfs_epp_path % cpu):
            val = True
        else:
            val = self._get_hwpreq().is_cpu_feature_supported("epp", cpu)

        return self._pcache.add("supported", cpu, val)

# ------------------------------------------------------------------------------------------------ #
# Get EPP policies through sysfs.
# ------------------------------------------------------------------------------------------------ #

    def _get_cpu_epp_policies(self, cpu):
        """Implements 'get_cpu_epp_policies()'."""

        if not self.is_epp_supported(cpu):
            return None

        if self._pcache.is_cached("epp_policies", cpu):
            return self._pcache.get("epp_policies", cpu)

        # Prefer using the names from the Linux kernel.
        path = self._sysfs_epp_policies_path % cpu
        line = self._pman.read(path, must_exist=False).strip()
        if line is None:
            policies = list(_EPP_POLICIES)
        else:
            policies = Trivial.split_csv_line(line, sep=" ")

        return self._pcache.add("epp_policies", cpu, policies)

    def get_epp_policies(self, cpus="all"):
        """
        Yield (CPU number, List of supported EPP policy names) pairs for CPUs in 'cpus'.
          * cpus - same as in 'get_epp_policy()'.
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield cpu, self._get_cpu_epp_policies(cpu)

    def get_cpu_epp_policies(self, cpu):
        """Return a list of all EPP policy names for CPU 'cpu."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epp_policies(cpu)

# ------------------------------------------------------------------------------------------------ #
# Get EPP policy through sysfs or MSR.
# ------------------------------------------------------------------------------------------------ #

    def _get_cpu_epp_policy_from_sysfs(self, cpu):
        """
        Returns EPP policy name for CPU 'cpu' by reading it from sysfs. Returns 'None' if the kernel
        does not support EPP policy.
        """

        try:
            policy = self._pman.read(self._sysfs_epp_path % cpu).strip()
        except ErrorNotFound:
            return None

        return policy

    def _get_cpu_epp_policy(self, cpu):
        """Returns EPP policy for CPU 'cpu'."""

        policies = self._get_cpu_epp_policies(cpu)
        if policies is None:
            return None

        if self._pcache.is_cached("epp_policy", cpu):
            policy = self._pcache.get("epp_policy", cpu)
        else:
            policy = self._get_cpu_epp_policy_from_sysfs(cpu)
            self._pcache.add("epp_policy", cpu, policy)

        if policy in policies:
            return policy

        if policy is not None:
            # We got a direct EPP value instead.
            return f"unknown EPP={policy}"

        # The kernel does not support EPP sysfs knobs. Try to figure the policy out.
        epp = self._get_cpu_epp(cpu)
        if epp is None:
            return None
        if epp in self._epp_rmap:
            return self._epp_rmap[epp]

        raise Error(f"unknown policy name for EPP value {epp} on CPU {cpu}{self._pman.hostmsg}")

    def get_epp_policy(self, cpus="all"):
        """
        Yield (CPU number, EPP policy name) pairs for CPUs in 'cpus'.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._get_cpu_epp_policy(cpu))

    def get_cpu_epp_policy(self, cpu):
        """Similar to 'get_epp_policy()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epp_policy(cpu)

# ------------------------------------------------------------------------------------------------ #
# Get EPP through MSR.
# ------------------------------------------------------------------------------------------------ #

    def _get_cpu_epp(self, cpu):
        """Implements 'get_cpu_epp()'."""

        # Find out if EPP should be read from 'MSR_HWP_REQUEST' or 'MSR_HWP_REQUEST_PKG'.
        hwpreq = self._get_hwpreq()
        if hwpreq.is_cpu_feature_pkg_controlled("epp", cpu):
            hwpreq = self._get_hwpreq_pkg()

        try:
            return hwpreq.read_cpu_feature("epp", cpu)
        except ErrorNotSupported:
            return None

    def get_epp(self, cpus="all"):
        """
        Yield (CPU number, EPP) pairs for CPUs in 'cpus'. The arguments are as follows:
          * cpus - the same as in 'set_epp()'.
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            yield (cpu, self._get_cpu_epp(cpu))

    def get_cpu_epp(self, cpu):
        """Similar to 'get_epp()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        return self._get_cpu_epp(cpu)

# ------------------------------------------------------------------------------------------------ #
# Set EPP through sysfs or MSR.
# ------------------------------------------------------------------------------------------------ #

    def _set_cpu_epp_via_sysfs(self, epp, cpu):
        """Set EPP to 'epp' for CPU 'cpu' via the sysfs file."""

        try:
            with self._pman.open(self._sysfs_epp_path % cpu, "r+") as fobj:
                fobj.write(str(epp))
        except ErrorNotFound:
            return None
        except Error as err:
            # We noticed that in some kernel version writing the same EPP value to the sysfs file
            # fails. This may be a kernel bug, but here is a work-around.
            if str(epp) == self._get_cpu_epp_policy_from_sysfs(cpu):
                return epp

            # Writing to the sysfs file failed, provide a meaningful error message.
            msg = f"failed to set EPP to {epp}{self._pman.hostmsg}:\n{err.indent(2)}"

            try:
                policies = self._get_cpu_epp_policies(cpu)
                policies = ", ".join(policies)
                msg += f"\nEPP must be an integer from 0 to 255 or one of: {policies}"
            except Error:
                pass

            raise Error(msg) from err

        return epp

    def _set_cpu_epp(self, epp, cpu):
        """Implements 'set_cpu_epp()'."""

        if not self.is_epp_supported(cpu):
            raise Error(f"CPU {cpu} does not support EPP")

        if Trivial.is_int(epp):
            Trivial.validate_value_in_range(int(epp), _EPP_MIN, _EPP_MAX, what="EPP")
        else:
            policies = self._get_cpu_epp_policies(cpu)
            policy = epp.lower()
            if policy not in policies:
                policy_names = ", ".join(self.get_cpu_epp_policies(cpu))
                raise Error(f"EPP policy '{epp}' is not supported{self._pman.hostmsg}, please "
                            f"provide one of the following EPP policy names: {policy_names}")

        if self._set_cpu_epp_via_sysfs(epp, cpu) == epp:
            # EPP was successfully set via sysfs.
            self._pcache.add("epp_policy", cpu, epp)
            return

        # Could not set EPP via sysfs because the running Linux kernel does not support it. Try to
        # set it via the MSR.
        hwpreq = self._get_hwpreq()
        hwpreq.disable_cpu_feature_pkg_control("epp", cpu)

        hwpreq.write_cpu_feature("epp", epp, cpu)

    def set_epp(self, epp, cpus="all"):
        """
        Set EPP for CPUs in 'cpus'. The arguments are as follows.
          * epp - the EPP value to set. Can be an integer, a string representing an integer, or one
                  of the EPP policy names.
          * cpus - list of CPUs and CPU ranges. This can be either a list or a string containing a
                   comma-separated list. For example, "0-4,7,8,10-12" would mean CPUs 0 to 4, CPUs
                   7, 8, and 10 to 12. 'None' and 'all' mean "all CPUs" (default).
        """

        for cpu in self._cpuinfo.normalize_cpus(cpus):
            self._set_cpu_epp(epp, cpu)

    def set_cpu_epp(self, epp, cpu):
        """Similar to 'set_epp()', but for a single CPU 'cpu'."""

        cpu = self._cpuinfo.normalize_cpu(cpu)
        self._set_cpu_epp(epp, cpu)

# ------------------------------------------------------------------------------------------------ #

    def __init__(self, pman=None, cpuinfo=None, msr=None, enable_cache=True):
        """
        The class constructor. The argument are as follows.
          * pman - the process manager object that defines the host to manage EPP for.
          * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
          * msr - an 'MSR.MSR()' object which should be used for accessing MSR registers.
          * enable_cache - this argument can be used to disable caching.
        """

        self._pman = pman
        self._cpuinfo = cpuinfo
        self._msr = msr
        self._enable_cache = enable_cache

        self._close_pman = pman is None
        self._close_cpuinfo = cpuinfo is None
        self._close_msr = msr is None

        self._hwpreq = None
        self._hwpreq_pkg = None
        self._epp_rmap = {code:name for name, code in _EPP_POLICIES.items()}

        sysfs_base = "/sys/devices/system/cpu/cpufreq/policy%d"
        self._sysfs_epp_path = sysfs_base + "/energy_performance_preference"
        self._sysfs_epp_policies_path = sysfs_base + "/energy_performance_available_preferences"

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

        if not self._cpuinfo:
            self._cpuinfo = CPUInfo.CPUInfo(pman=self._pman)

        # The per-CPU cache for read-only data, such as policies list. MSR implements its own
        # caching.
        self._pcache = _PropsCache.PropsCache(cpuinfo=self._cpuinfo, pman=self._pman,
                                              enable_cache=enable_cache)

        if self._cpuinfo.info["vendor"] != "GenuineIntel":
            raise ErrorNotSupported(f"unsupported vendor {cpuinfo.info['vendor']}{pman.hostmsg}. "
                                    f"Only Intel CPUs are supported.")

    def close(self):
        """Uninitialize the class object."""

        close_attrs = ("_hwpreq", "_hwpreq_pkg", "_msr", "_cpuinfo", "_pman", "_pcache")
        ClassHelpers.close(self, close_attrs=close_attrs)
