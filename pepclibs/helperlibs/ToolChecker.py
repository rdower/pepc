# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2020-2022 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Authors: Antti Laakso <antti.laakso@intel.com>
#          Artem Bityutskiy <artem.bityutskiy@linux.intel.com>

"""
This module provides a capability of checking if a tool is installed on a Linux host and providing a
meaningful OS package installation suggestion if it is not installed.
"""

import contextlib
from pathlib import Path
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported
from pepclibs.helperlibs import LocalProcessManager, ClassHelpers

#
# Tools information dictionary. Maps tool names to OS package names.
#

# Common for CentOS, Fedora, Debian, and Ubuntu.
_COMMON_PKGINFO = {
    "cat"       : "coreutils",
    "find"      : "findutils",
    "depmod"    : "kmod",
    "dmesg"     : "util-linux",
    "lscpu"     : "util-linux",
    "make"      : "make",
    "modprobe"  : "kmod",
    "phc2sys"   : "linuxptp",
    "rmmod"     : "kmod",
    "rsync"     : "rsync",
    "sync"      : "coreutils",
    "systemctl" : "systemd",
    "tc"        : "iproute2",
    "xargs"     : "findutils",
}

# CentOS and Fedora.
_FEDORA_PKGINFO = {"sch_etf.ko" : "kernel-modules-extra"}

# Ubuntu and Debian.
_DEBIAN_PKGINFO = {"sch_etf.ko" : "linux-modules"}

_FEDORA_PKGINFO.update(_COMMON_PKGINFO)
_DEBIAN_PKGINFO.update(_COMMON_PKGINFO)

_PKGINFO = {
    "Ubuntu" :           _DEBIAN_PKGINFO,
    "Debian GNU/Linux" : _DEBIAN_PKGINFO,
    "Fedora" :           _FEDORA_PKGINFO,
    "CentOS Linux" :     _FEDORA_PKGINFO,
}

class ToolChecker:
    """
    This class provides a capability of checking if a tool is installed on a Linux host and
    providing a meaningful suggestion if it is not installed.
    """

    def _read_os_release(self, sysroot="/"):
        """
        Read and parse the '/etc/os-release' file, and return its contents as a dictionary.
        """

        paths = ("/usr/lib/os-release", "/etc/os-release")
        paths = [Path(sysroot) / path.lstrip("/") for path in paths]
        osinfo = {}

        for path in paths:
            with contextlib.suppress(self._pman.Error):
                with self._pman.open(path, "r") as fobj:
                    for line in fobj:
                        key, val = line.rstrip().split("=")
                        osinfo[key] = val.strip('"')
            if osinfo:
                break

        if not osinfo:
            files = "\n".join([str(path) for path in paths])
            raise Error(f"cannot discover OS version{self._pman.hostmsg}, these files were "
                        f"checked:\n{files}")

        return osinfo

    def _get_osname(self):
        """Returns the OS name of the SUT."""

        if self._osname:
            return self._osname

        osinfo = self._read_os_release()
        return osinfo.get("NAME")

    def tool_to_pkg(self, tool):
        """
        Returns the OS package name providing 'tool'. Returns 'None' if package name is was not
        found.
        """

        osname = self._get_osname()
        if osname not in _PKGINFO:
            return None

        return _PKGINFO[osname].get(tool)

    def check_tool(self, tool):
        """
        Check if tool 'tool' is available on the SUT. Returns tool path if it is available, raises
        an 'ErrorNotSupported' exception otherwise.
        """

        if tool is self._cache:
            return self._cache[tool]

        path = self._pman.which(tool, must_find=False)
        if path:
            self._cache[tool] = path
            return path

        msg = f"failed to find tool '{tool}'{self._pman.hostmsg}"

        pkgname = self.tool_to_pkg(Path(tool).name)
        if pkgname:
            msg += f".\nTry to install package '{pkgname}'{self._pman.hostmsg}."

        raise ErrorNotSupported(msg)

    def __init__(self, pman=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the host to check for the tools on.
        """

        self._pman = pman
        self._close_pman = pman is None
        self._osname = None
        # Tools name to tool path cache.
        self._cache = {}

        if not self._pman:
            self._pman = LocalProcessManager.LocalProcessManager()

    def close(self):
        """Uninitialize the class object."""
        ClassHelpers.close(self, close_attrs=("_pman",))

    def __enter__(self):
        """Enter the runtime context."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context."""
        self.close()
