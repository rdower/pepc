#!/usr/bin/env python3
#
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Niklas Neronin <niklas.neronin@intel.com>

"""Tests for the public methods of the 'PStates' module."""

import pytest
from common import build_params, get_datasets, get_pman, prop_is_supported
from pcstates_common import get_fellows, set_and_verify
from pepclibs import CPUInfo, PStates

@pytest.fixture(name="params", scope="module", params=get_datasets())
def get_params(hostname, request):
    """Yield a dictionary with information we need for testing."""

    dataset = request.param
    with get_pman(hostname, dataset) as pman, CPUInfo.CPUInfo(pman=pman) as cpuinfo, \
         PStates.PStates(pman=pman, cpuinfo=cpuinfo) as psobj:
        params = build_params(hostname, dataset, pman, cpuinfo)
        params["fellows"] = get_fellows(params, cpuinfo, cpu=0)

        params["psobj"] = psobj
        params["props"] = psobj.get_cpu_props(psobj.props, 0)

        yield params

def _set_and_verify_data(params):
    """
    Yields data for the 'test_pstates_set_and_verify()' test-case. Yields tuples of the following
    format: '(pname, val1, val2)'.
    """

    props = params["props"]

    if prop_is_supported("turbo", props):
        yield "turbo", "off", "on"

    if prop_is_supported("epp_policy", props):
        yield "epp_policy", props["epp_policy"]["epp_policies"][0], \
              props["epp_policy"]["epp_policies"][-1]
    elif prop_is_supported("epp", props):
        yield "epp", 0, 128

    if prop_is_supported("epb_policy", props):
        yield "epb_policy", props["epb_policy"]["epb_policies"][0], \
              props["epb_policy"]["epb_policies"][-1]
    elif prop_is_supported("epb", props):
        yield "epb", 0, 15

    if prop_is_supported("governor", props):
        yield "governor", props["governor"]["governors"][0], props["governor"]["governors"][-1]

    freq_pairs = (("min_freq", "max_freq"), ("min_uncore_freq", "max_uncore_freq"))
    for pname_min, pname_max in freq_pairs:
        if prop_is_supported(pname_min, props):
            min_limit = props[f"{pname_min}_limit"][f"{pname_min}_limit"]
            max_limit = props[f"{pname_max}_limit"][f"{pname_max}_limit"]

            # Right now we do not know how the SUT min. and max frequency is configured, so we have
            # to be careful to avoid failures related to setting min. frequency higher than the
            # currently configured max. frequency. The next two "yields" will make sure the SUT has
            # min. frequency set to the minimum supported frequency, and max. frequency set to the
            # maximum supported frequency.
            yield pname_min, min_limit, min_limit
            yield pname_max, max_limit, max_limit
            # Now we can test the properties by setting them to different values.
            yield pname_min, max_limit, min_limit
            yield pname_max, min_limit, max_limit

def test_pstates_set_and_verify(params):
    """Test for if 'get_props()' returns the same values set by 'set_props()'."""

    for pname, val1, val2 in _set_and_verify_data(params):
        scope = params["psobj"].props[pname]["scope"]
        fellows = params["fellows"][scope]

        set_and_verify(params["psobj"], pname, val1, val2, fellows)
