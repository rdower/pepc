# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module includes the "cstates" 'pepc' command implementation.
"""

import logging
import contextlib
from pepclibs.helperlibs.Exceptions import Error
from pepclibs.msr import MSR
from pepclibs import CStates, CPUInfo
from pepctool import _PepcCommon, _PepcPrinter, _PepcSetter

_LOG = logging.getLogger()

def cstates_info_command(args, pman):
    """Implements the 'cstates info' command."""

    # The output format to use.
    fmt = "yaml" if args.yaml else "human"

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        pobj = CStates.CStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        csprint = _PepcPrinter.CStatesPrinter(pobj, cpuinfo, fmt=fmt)
        stack.enter_context(csprint)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        mnames = None
        if args.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(args.mechanisms, pobj)

        printed = 0
        if not hasattr(args, "oargs") and args.csnames == "default":
            # No options were specified. Print all the information. Skip the unsupported ones as
            # they add clutter.
            printed += csprint.print_cstates(csnames="all", cpus=cpus, group=True)
            printed += csprint.print_props(pnames="all", cpus=cpus, mnames=mnames,
                                           skip_unsupported=True, group=True)
        else:
            if args.csnames != "default":
                # args.csname is "default" if '--csnames' option was not specified, and 'None' if it
                # was specified, but without an argument.
                csnames = args.csnames
                if args.csnames is None:
                    csnames = "all"
                printed += csprint.print_cstates(csnames=csnames, cpus=cpus)

            pnames = list(getattr(args, "oargs", []))
            pnames = _PepcCommon.expand_subprops(pnames, pobj.props)
            if pnames:
                printed += csprint.print_props(pnames=pnames, cpus=cpus, mnames=mnames,
                                               skip_unsupported=False)

        if not printed:
            _LOG.info("No C-states properties supported%s.", pman.hostmsg)

def cstates_config_command(args, pman):
    """Implements the 'cstates config' command."""

    if not hasattr(args, "oargs"):
        raise Error("please, provide a configuration option")

    # The '--enable' and '--disable' options.
    enable_opts = {}
    # Options to set (excluding '--enable' and '--disable').
    set_opts = {}
    # Options to print (excluding '--enable' and '--disable').
    print_opts = []

    opts = getattr(args, "oargs", {})
    for optname, optval in opts.items():
        if optname in {"enable", "disable"}:
            enable_opts[optname] = optval
        elif optval is None:
            print_opts.append(optname)
        else:
            set_opts[optname] = optval

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        if args.override_cpu_model:
            _PepcCommon.override_cpu_model(cpuinfo, args.override_cpu_model)

        msr = MSR.MSR(pman, cpuinfo=cpuinfo)
        stack.enter_context(msr)

        pobj = CStates.CStates(pman=pman, msr=msr, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        mnames = None
        if args.mechanisms:
            mnames = _PepcCommon.parse_mechanisms(args.mechanisms, pobj)

        csprint = _PepcPrinter.CStatesPrinter(pobj, cpuinfo)
        stack.enter_context(csprint)

        all_cstates_printed = False
        for optname in list(enable_opts):
            if not enable_opts[optname]:
                # Handle the special case of '--enable' and '--disable' option without arguments. In
                # this case we just print the C-states enable/disable status.
                if not all_cstates_printed:
                    csprint.print_cstates(csnames="all", cpus=cpus)
                    all_cstates_printed = True
                del enable_opts[optname]

        if print_opts:
            csprint.print_props(pnames=print_opts, mnames=mnames, cpus=cpus, skip_unsupported=False)

        if set_opts or enable_opts:
            csset = _PepcSetter.CStatesSetter(pobj, cpuinfo, csprint, msr=msr)
            stack.enter_context(csset)

        if enable_opts:
            for optname, optval in enable_opts.items():
                enable = optname == "enable"
                csset.set_cstates(csnames=optval, cpus=cpus, enable=enable, mnames=mnames)

        if set_opts:
            csset.set_props(set_opts, cpus=cpus, mnames=mnames)

    if enable_opts or set_opts:
        _PepcCommon.check_tuned_presence(pman)

def cstates_save_command(args, pman):
    """Implements the 'cstates save' command."""

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        pobj = CStates.CStates(pman=pman, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        fobj = None
        if args.outfile:
            try:
                # pylint: disable=consider-using-with
                fobj = open(args.outfile, "w", encoding="utf-8")
            except OSError as err:
                msg = Error(err).indent(2)
                raise Error(f"failed to open file '{args.outfile}':\n{msg}") from None

            stack.enter_context(fobj)

        csprint = _PepcPrinter.CStatesPrinter(pobj, cpuinfo, fobj=fobj, fmt="yaml")
        stack.enter_context(csprint)

        cpus = _PepcCommon.get_cpus(args, cpuinfo, default_cpus="all")

        printed = 0
        printed += csprint.print_cstates(cpus=cpus, skip_ro=True)
        printed += csprint.print_props(cpus=cpus, skip_ro=True, skip_unsupported=True)

        if not printed:
            _LOG.info("No writable C-states properties supported%s.", pman.hostmsg)

def cstates_restore_command(args, pman):
    """Implements the 'cstates restore' command."""

    if not args.infile:
        raise Error("please, specify the file to restore from (use '-' to restore from standard "
                    "input)")

    with contextlib.ExitStack() as stack:
        cpuinfo = CPUInfo.CPUInfo(pman=pman)
        stack.enter_context(cpuinfo)

        msr = MSR.MSR(pman, cpuinfo=cpuinfo)
        stack.enter_context(msr)

        pobj = CStates.CStates(pman=pman, msr=msr, cpuinfo=cpuinfo)
        stack.enter_context(pobj)

        csprint = _PepcPrinter.CStatesPrinter(pobj, cpuinfo)
        stack.enter_context(csprint)

        csset = _PepcSetter.CStatesSetter(pobj, cpuinfo, csprint, msr=msr)
        stack.enter_context(csset)

        csset.restore(args.infile)
