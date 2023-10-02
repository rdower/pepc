# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2021 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module contains misc. helper functions with the common theme of representing something in a
human-readable format, or turning human-oriented data into a machine format.
"""

import logging
from itertools import groupby
from pepclibs.helperlibs import Trivial
from pepclibs.helperlibs.Exceptions import Error

_LOG = logging.getLogger()

# The units this module supports.
SUPPORTED_UNITS = {
    "s":  "second",
    "Hz": "hertz",
    "W" : "watt",
}

_SIPFX_LARGE = ["k", "M", "G", "T", "E"]
_SIPFX_SMALL = ["m", "u", "n"]
_SIPFX_SCALERS = {
    "E": 1000000000000000,
    "T": 1000000000000,
    "G": 1000000000,
    "M": 1000000,
    "k": 1000,
    "m": 0.001,
    "u": 0.000001,
    "n": 0.000000001,
}
_SIPFX_FULLNAMES = {
    "E": "exa",
    "T": "tera",
    "G": "giga",
    "M": "mega",
    "k": "kilo",
    "m": "milli",
    "u": "micro",
    "n": "nano",
}

_SIZE_UNITS = ["KiB", "MiB", "GiB", "TiB", "EiB"]

# pylint: disable=undefined-loop-variable, consider-using-f-string
def bytesize(size, precision=1, sep=""):
    """
	Transform size in bytes into a human-readable form. The 'precision' argument can be use to
    specify the amount of fractional digits to print.
	"""

    if size == 1:
        return "1 byte"

    if size < 512:
        return "%d bytes" % size

    for unit in _SIZE_UNITS:
        size /= 1024.0
        if size < 1024:
            break

    if precision <= 0:
        return "%d%s%s" % (int(size), sep, unit)

    pattern = "%%.%df %%s" % int(precision)
    return pattern % (size, unit)
# pylint: enable=undefined-loop-variable

def parse_bytesize(size):
    """
    This function does the opposite to what the 'bytesize()' function does - turns a
    human-readable string describing a size in bytes into an integer amount of bytes.
    """

    size = str(size).strip()
    orig_size = size
    multiplier = 1

    for idx, unit in enumerate(_SIZE_UNITS):
        if size.lower().endswith(unit.lower()):
            multiplier = pow(1024, idx + 1)
            size = size[:-3]
            break

    try:
        return int(float(size) * multiplier)
    except ValueError:
        raise Error("cannot interpret bytes count '%s', please provide a number and "
                    "possibly the unit: %s" % (orig_size, ", ".join(_SIZE_UNITS))) from None

def separate_si_prefix(unit):
    """
    Split any SI-unit prefix from the base unit and return a tuple containing both. If 'unit' does
    not contain any SI-unit prefixes, then returns the prefix as 'None'. Example behaviour:
     * "kHz" -> "k", "Hz"
     * "Hz" -> None, "Hz"
    """

    if len(unit) < 2:
        return None, unit

    sipfx = unit[0]
    base_unit = unit[1:]

    if sipfx not in _SIPFX_SCALERS:
        return None, unit

    if base_unit not in SUPPORTED_UNITS:
        _LOG.warning("unsupported unit '%s' was split into SI-prefix '%s' and base unit '%s'",
                     unit, sipfx, base_unit)

    return sipfx, base_unit

def num2si(value, unit=None, sep="", decp=1):
    """
    Convert a number into a human-readable form using suffixes like "k" (Kilo), "M" (Mega), etc.
    The arguments are as follows.
      * value - an integer or floating point value to convert.
      * unit - the unit used with 'value', including any SI-prefixes.
      * sep - the separator string to use between the resulting number and its unit.
      * decp - maximum number of decimal places the result should include.

    Return the result as a string.
    """

    if not Trivial.is_num(value):
        raise Error("bad input - not a number")
    if sep and not unit:
        raise Error("please, specify the separator only if unit was specified")
    if decp < 1 or decp > 8:
        raise Error("please, specify at max. 8 decimal places")

    if unit is None:
        unit = ""

    sipfx, base_unit = separate_si_prefix(unit)
    value = float(value)

    if sipfx:
        factor = _SIPFX_SCALERS[sipfx]
        if value > 500 or value < 1:
            value *= factor

    pfx = None
    if value > 500:
        for pfx in _SIPFX_LARGE:
            value /= 1000.0
            if value < 1000:
                break
    elif value < 1:
        for pfx in _SIPFX_SMALL:
            value *= 1000.0
            if value >= 1:
                break
    else:
        pfx = sipfx

    result = f"%.{decp}f" % value
    result = result.rstrip("0").rstrip(".")
    if pfx:
        result += sep + pfx
    if base_unit:
        result += base_unit
    return result

def scale_si_val(val, unit):
    """
    Scale 'val' which has unit 'unit'. The data will be scaled so that the unit representing the
    data does not contain any SI-unit prefix. Example behaviour:
     * 5, "kHz" -> 5000
     * 10, "ms" -> 0.01
     * 10, "s" -> 10
    """

    prefix, _ = separate_si_prefix(unit)

    if not prefix:
        return val

    scale_factor = _SIPFX_SCALERS[prefix]
    return val * scale_factor

def duration(seconds, s=True, ms=False):
    """
    Transform duration in seconds to the human-readable format. The 's' and 'ms' arguments control
    whether seconds/milliseconds should be printed or not.
    """

    if not isinstance(seconds, int):
        msecs = int((float(seconds) - int(seconds)) * 1000)
    else:
        msecs = 0

    (mins, secs) = divmod(int(seconds), 60)
    (hours, mins) = divmod(mins, 60)
    (days, hours) = divmod(hours, 24)

    result = ""
    if days:
        result += "%d days " % days
    if hours:
        result += "%dh " % hours
    if mins:
        result += "%dm " % mins
    if s or seconds < 60:
        if ms or seconds < 1 or (msecs and seconds < 10):
            result += "%f" % (secs + float(msecs) / 1000)
            result = result.rstrip("0").rstrip(".")
            result += "s"
        elif secs:
            result += "%ds " % secs

    return result.strip()

_NSTIME_UNITS = ["us", "ms", "s"]

def duration_ns(value, sep=""):
    """
    Transform a supposedly large integer amount of nanoseconds into a human-readable form using
    suffixes like "us" (microseconds), etc.
    """

    scaler = None
    if value >= 500:
        for scaler in _NSTIME_UNITS:
            value /= 1000.0
            if value < 1000:
                break

    result = "%f" % value
    result = result.rstrip("0").rstrip(".")
    if not scaler:
        scaler = "ns"
    result += sep + scaler
    return result

def _tokenize(hval, specs, name=None, multiple=True):
    """
    Split human-provided value 'hval' according unit names in the 'specs' dictionary. Returns the
    dictionary of tokens.

    Example.
        * hval = "1d 4m 1s"
        * specs = {"d" : "days", "m" : "minutes", "s" : "seconds"}
        * Result: {'d': '1', 'm': '4', 's': '1'}

    The 'multiple' argument can be used to limit the input value to just a single number and unit.
    In the above example, if 'multiple' is 'False', this function would raise an error.
    """

    if name:
        name = f" {name}"
    else:
        name = ""

    tokens = {}
    rest = hval.lower()
    for spec in specs:
        split = rest.split(spec.lower(), 1)
        if len(split) > 1:
            tokens[spec] = split[0]
            rest = split[1]
        else:
            rest = split[0]

    if rest.strip():
        raise Error(f"failed to parse{name} value '{hval}'")

    if not multiple and len(tokens) > 1:
        raise Error(f"failed to parse{name} value '{hval}': should be one value")

    for idx, (spec, val) in enumerate(tokens.items()):
        if idx < len(tokens) - 1:
            # This is not the last element, it must be an integer.
            try:
                tokens[spec] = int(val)
            except:
                raise Error(f"failed to parse{name} value '{hval}': non-integer amount of "
                            f"{specs[spec]}") from None
        else:
            # This is the last element. It can be a floating point or integer.
            try:
                tokens[spec] = float(val)
            except:
                raise Error(f"failed to parse{name} value '{hval}': non-numeric amount of "
                            f"{specs[spec]}") from None

            if Trivial.is_int(val):
                tokens[spec] = int(val)

    return tokens

def parse_duration(htime, default_unit="s", name=None):
    """
    This function does the opposite to what 'duration()' does - parses the human time string and
    returns integer number of seconds. This function supports the following specifiers:
      * d - days
      * h - hours
      * m - minutes
      * s - seconds.

    Valid 'htime' value examples: 5, 1d, 3s, 5h 3s, 6m1s

    If 'htime' is just a number without a specifier, it is assumed to be in seconds. But the
    'default_unit' argument can be used to specify a different default unit. The optional 'what'
    argument can be used to pass a name that will be used in error message.
    """

    if Trivial.is_num(htime):
        htime = f"{htime}{default_unit}"

    if name is None:
        name = "time"

    specs = {"d" : "days", "h" : "hours", "m" : "minutes", "s" : "seconds"}
    tokens = _tokenize(htime, specs, name=name)

    days  = tokens.get("d", 0)
    hours = tokens.get("h", 0)
    mins  = tokens.get("m", 0)
    secs  = tokens.get("s", 0)
    result = days * 24 * 60 * 60 + hours * 60 * 60 + mins * 60 + secs

    if Trivial.is_int(result):
        result = int(result)
    return result

def parse_duration_ns(htime, default_unit="ns", name=None):
    """
    Similar to 'parse_duration()', but supports different specifiers and returns integer amount of
    nanoseconds. The supported specifiers are:
      * s - seconds
      * ms - milliseconds
      * us - microseconds
      * ns - nanoseconds
    """

    if Trivial.is_num(htime):
        htime = f"{htime}{default_unit}"

    if name is None:
        name = "time"

    specs = {"ms" : "milliseconds", "us" : "microseconds", "ns" : "nanoseconds", "s" : "seconds"}
    tokens = _tokenize(htime, specs, name=name)

    ms = tokens.get("ms", 0)
    us = tokens.get("us", 0)
    ns = tokens.get("ns", 0)
    s = tokens.get("s", 0)
    result = s * 1000 * 1000 * 1000 + ms * 1000 * 1000 + us * 1000 + ns

    if Trivial.is_int(result):
        result = int(result)
    return result

def parse_freq(hfreq, default_unit="Hz", name=None):
    """
    Turn a user-provided frequency string into 'int' or 'float' amount of hertz and return the
    result. The 'hfreq' string is allowed to include the unit, for example 'GHz' or 'megaherz'.

    Optional 'name' argument may include a short description of the 'hfreq' value, which will be
    used in error messages.
    """

    if Trivial.is_num(hfreq):
        hfreq = f"{hfreq}{default_unit}"

    if name is None:
        name = "frequency"

    specs = {"GHz" : "gigahertz", "MHz" : "megahertz", "kHz" : "kilohertz", "Hz" : "Hertz"}
    tokens = _tokenize(hfreq, specs, name=name, multiple=False)

    scalers = {"Hz" : 1, "kHz" : 1000, "MHz" : 1000000, "GHz" : 1000000000}

    freq = 0
    for unit, val in tokens.items():
        freq += val * scalers[unit]

    if Trivial.is_int(freq):
        freq = int(freq)
    return freq

def parse_human(hval, unit, target_unit=None, integer=True, name=None):
    """
    Convert a user-provided value 'hval' into an integer of float amount of 'unit' units (hertz,
    seconds, etc). The arguments are as follows.
      * hval - the value to convert. Can be a of a string, int, float type. If it is a string, may
               include the unit.
      * unit - the unit of 'hval', including any SI prefixes.
      * target_unit - the unit of the result, including any SI prefixes (same 'unit' without a SI
                      prefix by default).
      * integer - if 'True', round the result to the nearest integer and return an 'int' type,
                  otherwise return the result as a floating point number ('float' type).
      * name - an optional name associated with the value, will be used only in case of an error for
               formatting a nicer message.

    Examples.
      * 100,         unit="Hz",                    integer=False  -> 100.0
      * 100,         unit="kHz",                   integer=True   -> 100000
      * "100kHz",    unit="Hz", target_unit="kHz", integer=False  -> 100.0
      * "100MHz",    unit="Hz", target_unit="kHz", integer=False  -> 100000.0
      * "1m",        unit="s",  target_unit="s",   integer=True    -> 60
      * "100s",      unit="s",  target_unit="ns",  integer=True    -> 100000000000
      * "1us",       unit="s",  target_unit="ns",  integer=True    -> 1000
      * "1h 10m 5s", unit="s",  target_unit="s",   integer=True    -> 4205
      * "1h 10m 5s", unit="s",  target_unit="us",  integer=True    -> 4205000000
      * "101ns",     unit="s",  target_unit="ns",  integer=True    -> 101
      * "101ns",     unit="s",  target_unit="us",  integer=False   -> 0.101
    """

    sipfx, base_unit = separate_si_prefix(unit)
    target_sipfx, target_base_unit = None, base_unit

    if target_unit:
        target_sipfx, target_base_unit = separate_si_prefix(target_unit)
        if target_base_unit != base_unit:
            raise Error(f"the target base unit has to be '{base_unit}', not '{target_base_unit}")

    if Trivial.is_num(hval):
        if sipfx:
            hval = f"{hval}{sipfx}"
        hval = f"{hval}{base_unit}"

    # Create the specifiers dictionary.
    specs = {}
    scalers = {}
    fullname = SUPPORTED_UNITS.get(base_unit, base_unit)
    for pfx, pfx_fullname in _SIPFX_FULLNAMES.items():
        spec = f"{pfx}{base_unit}"
        if fullname != base_unit:
            specs[spec] = f"{pfx_fullname}{fullname}"
        else:
            specs[spec] = spec
        scalers[spec] = _SIPFX_SCALERS[pfx]

    # For time, allow day/hour/minute specifiers too.
    if unit == "s":
        specs["d"] = "day"
        specs["h"] = "hour"
        specs["m"] = "minute"
        scalers["d"] = 24 * 60 * 60
        scalers["h"] = 60 * 60
        scalers["m"] = 60
        # Allow for multiple specifiers for time, like in "1d 5h".
        multiple = True
    else:
        multiple = False

    specs[base_unit] = fullname
    scalers[base_unit] = 1
    tokens = _tokenize(hval, specs, name, multiple=multiple)

    result = 0.0
    for base_unit, val in tokens.items():
        result += val * scalers[base_unit]

    if target_sipfx:
        result /= _SIPFX_SCALERS[target_sipfx]

    if integer:
        result = round(result)

    return result

def rangify(numbers):
    """
    Turn list of numbers in 'numbers' to a string of comma-separated ranges. Numbers can be integers
    or strings. E.g. list of numbers [0,1,2,4] is translated to "0-2,4".
    """

    try:
        numbers = [int(number) for number in numbers]
    except (ValueError, TypeError) as err:
        raise Error(f"failed to translate numbers to ranges, expected list of numbers, got "
                    f"'{numbers}'") from err

    range_strs = []
    numbers = sorted(numbers)
    for _, pairs in groupby(enumerate(numbers), lambda x:x[0]-x[1]):
        # The 'pairs' is an iterable of tuples (enumerate value, number). E.g. 'numbers'
        # [5,6,7,8,10,11,13] would result in three iterable groups:
        # ((0, 5), (1, 6), (2, 7), (3, 8)) , ((4, 10), (5, 11)) and  (6, 13)

        nums = [val for _, val in pairs]
        if len(nums) > 2:
            range_strs.append(f"{nums[0]}-{nums[-1]}")
        else:
            for num in nums:
                range_strs.append(str(num))

    return ",".join(range_strs)

def uncapitalize(sentence):
    """
    Return 'sentence' but with the first letter in the first word modified from capital to small.
    This function includes some heuristics to avoid un-capitalizing words like "C1" or "C-state".
    """

    # Seprate out the first word by splitting the sentence. If the word include a hyphen, separate
    # out the first part. E.g., "C-state residency" will become just "C".
    word = sentence
    for separator in (" ", "-"):
        split = word.split(separator)
        if len(split) < 1:
            return sentence
        word = split[0]
        if len(word) < 2:
            return sentence

    # Do nothing if the first character is lowercase or if both first and second characters are
    # upper case, which would mean this 'word' is an abbreviation, such as "DNA".
    if word[0].islower() or word[1].isupper():
        return sentence

    # Do nothing if there are digits in the word.
    for char in word:
        if char.isdigit():
            return sentence

    return sentence[0].lower() + sentence[1:]
