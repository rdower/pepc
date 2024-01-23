# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Tero Kristo <tero.kristo@linux.intel.com>

"""
This feature includes the "tpmi" 'pepc' command implementation.
"""

from pepclibs import Tpmi

def tpmi_ls_command(args, pman):
    """
    Implements the 'tpmi info' command. Arguments are as follows.
      * args - command line arguments.
      * pman - process manager.
    """

    tpmi_obj = Tpmi.Tpmi(pman=pman)

    features, no_specs = tpmi_obj.get_features()
    if features:
        print("Following features are fully supported:")
        txt = ", ".join(features)
        print(f"  {txt}")
    if no_specs and args.all:
        print("Following features are supported by hardware, but have no spec data available:")
        txt = ", ".join(no_specs)
        print(f"  {txt}")
