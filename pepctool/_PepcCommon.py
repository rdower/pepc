# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
Misc. helpers shared between various 'pepc' commands.
"""

import logging
from pepclibs.helperlibs.Exceptions import Error, ErrorNotFound
from pepclibs.helperlibs import Systemctl, Trivial, ArgParse

_LOG = logging.getLogger()

def check_tuned_presence(pman):
    """Check if the 'tuned' service is active, and if it is, print a warning message."""

    try:
        with Systemctl.Systemctl(pman=pman) as systemctl:
            if systemctl.is_active("tuned"):
                _LOG.warning("the 'tuned' service is active%s! It may override the changes made by "
                             "'pepc'.\nConsider having 'tuned' disabled while experimenting with "
                             "power management settings.", pman.hostmsg)
    except ErrorNotFound:
        pass
    except Error as err:
        _LOG.warning("failed to check for 'tuned' presence:\n%s", err.indent(2))

def parse_cpus_string(string):
    """
    Parse string of comma-separated numbers and number ranges, and return them as a list of
    integers.
    """

    if string == "all":
        return string
    return ArgParse.parse_int_list(string, ints=True, dedup=True)

def get_cpus(args, cpuinfo, default_cpus="all", offlined_ok=False):
    """
    Get list of CPUs based on requested packages, cores and CPUs numbers. If no CPUs, cores and
    packages are requested, returns 'default_cpus'.

    By default, requested offlined CPUs are not allowed and will cause an exception. Use
    'offlined_ok=True' to allow offlined CPUs. When the argument is "all", all online CPUs are
    included and no exception is raised for offline CPUs, with 'offlined_ok=True' "all" will include
    online and offline CPUs. For package and core 'offlined_ok=True' does nothing, due to offline
    CPUs not having a package and core number.
    """

    cpus = []

    if args.cpus:
        cpus += cpuinfo.normalize_cpus(cpus=parse_cpus_string(args.cpus), offlined_ok=offlined_ok)

    if args.cores:
        packages = parse_cpus_string(args.packages)
        if not packages:
            if cpuinfo.get_packages_count() != 1:
                raise Error("'--cores' must be used with '--packages'")
            packages = (0,)

        cpus += cpuinfo.cores_to_cpus(cores=parse_cpus_string(args.cores), packages=packages)

    if args.packages and not args.cores:
        cpus += cpuinfo.packages_to_cpus(packages=parse_cpus_string(args.packages))

    if not cpus and default_cpus is not None:
        cpus = cpuinfo.normalize_cpus(parse_cpus_string(default_cpus), offlined_ok=offlined_ok)

    if args.core_siblings:
        return cpuinfo.select_core_siblings(cpus, parse_cpus_string(args.core_siblings))

    return Trivial.list_dedup(cpus)

def override_cpu_model(cpuinfo, model):
    """
    Override the CPU model. The arguments are as follows.
      * cpuinfo - CPU information object generated by 'CPUInfo.CPUInfo()'.
      * model - the target CPU model, can be integer or string representation of an decimal or hex.
    """

    model = str(model)
    try:
        cpuinfo.info["model"] = int(model)
    except (ValueError, TypeError):
        try:
            cpuinfo.info["model"] = int(model, 16)
        except (ValueError, TypeError):
            raise Error(f"bad CPU model '{model}': should be an integer") from None

    cpuinfo.cpudescr += f" overridden to {cpuinfo.info['model']:#x}"
    _LOG.warning(cpuinfo.cpudescr)

def expand_subprops(pnames, props):
    """
    Expand list of property names 'pnames' with sub-property names. The arguments are as follows.
      * pnames - a collection of property names to expand.
      * props - the properties dictionary (e.g., 'CStates.PROPS').

      This helper function takes a list of property names in 'pnames', and if any property in
      'pnames' has a sub-property, the sub-property names are inserted into 'pnames' right after the
      main property name. Well, the sub-property names are inserted to a copy of 'pnames', and the
      resulting copy is returned.
    """

    expanded = []

    for pname in pnames:
        expanded.append(pname)

        spnames = []
        prop = props.get(pname)
        if prop:
            spnames = prop.get("subprops", [])

        for spname in spnames:
            expanded.append(spname)

    return expanded
