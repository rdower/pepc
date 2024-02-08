# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=100 et ai si
#
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: BSD-3-Clause
#
# Author: Tero Kristo <tero.kristo@linux.intel.com>

"""
Provide capability for reading and writing TPMI registers on Intel CPUs. TPMI stands for "Topology
Aware Register and PM Capsule Interface" and is a  memory mapped interface for accessing power
management features on Intel CPUs, in addition to the existing MSRs.

Terminology.
  * feature - a group of TPMI registers exposed by the processor via PCIe VSEC (Vendor-Specific
              Extended Capabilities) as a single capability. Typically TPMI feature corresponds to
              a real processor feature. For example, "uncore" TPMI feature includes processor
              registers related to uncore frequency scaling. The "rapl" TPMI feature includes
              processor registers related to processor's Running Average Power Limit (RAPL) feature.
              The "sst" feature includes processor registers related to Intel Speed Select
              Technology (SST) feature.

  * feature ID - a unique integer number assigned to a feature.

  * spec file - a YAML file describing the registers and bitfields for a TPMI feature. Each
                supported feature has a spec file, and each spec file corresponds to a feature. A
                spec file is also required to decode the TPMI feature's PCIe VSEC table.

  * spec directory - a directory containing one or multiple spec files. There may be multiple spec
                     directories.

  * feature dictionary - a dictionary describing a TPMI feature registers, bit fields and other
                         details. Feature dictionary is formed based on the feature spec file
                         contents.

  * feature map - a dictionary that maps known feature names to corresponding debugfs file paths on
                  the target host. This data structure is built by scanning the TPMI debugfs
                  hierarcy of the target host.

  * spec dictionary - a dictionary including basic TPMI spec file information - name, ID, and
                      description of the feature it describes, path to the spec file. Spec
                      dictionaries are built by partially reading the spec file during the initial
                      scanning of spec directories.

  * supported feature - a TPMI feature supported by the processor.

  * known feature - a supported feature for which the spec file was found, so that the feature can
                    be decoded and used.

  * unknown feature - a supported feature for which the spec file was not found.
"""

import os
import re
import stat
import logging
import contextlib
from pathlib import Path
import yaml
from pepclibs.helperlibs import YAML, ClassHelpers, FSHelpers, ProjectFiles, Trivial, Human
from pepclibs.helperlibs.Exceptions import Error, ErrorNotSupported

# Users can define this environment variable to extend the default spec files.
_SPECS_PATH_ENVVAR = "PEPC_TPMI_DATA_PATH"

# Maximum count of spec files per directory.
_MAX_SPEC_FILES = 256
# Maximum count of non-YAML files (extention is other than '.yml' or '.yaml') per directory.
_MAX_NON_YAML = 32
# Maximum count of spec file loading/parsing errors during scanning per spec directory.
_MAX_SCAN_LOAD_ERRORS = 4
# Maximum spec file size in bytes.
_MAX_SPEC_FILE_BYTES = 4 * 1024 * 1024 * 1024

_LOG = logging.getLogger()

def _find_spec_dirs():
    """Find paths to TPMI spec directories and return them as a list."""

    specdirs = []

    # Add the user-defined spec directory. This directory is optional and can be used for extending
    # the standard spec files.
    path = os.getenv(_SPECS_PATH_ENVVAR)
    if path:
        path = Path(path)
        if not path.exists():
            _LOG.warning("TPMI spec files path '%s' specified in the '%s' environment "
                         "variable does not exist, ignoring it", path, _SPECS_PATH_ENVVAR)
        else:
            specdirs.append(path)

    # Find the standard spec-files.
    specdirs.append(ProjectFiles.find_project_data("pepc", "tpmi", what="TPMI spec files"))

    return specdirs

def _load_sdict(specpath):
    """
    Partially load spec file at 'specpath', just enough to get feature name, description, and ID.
    Create and return the spec dictionary for the spec file.

    The implementation is optimized to avoid loading the entire spec file and instead, only look at
    the beginning of the file.
    """

    fobj = None

    # Basic spec file validation.
    try:
        st = specpath.stat()
    except OSError as err:
        msg = Error(str(err)).indent(2)
        raise Error(f"failed to open spec file '{specpath}:\n{msg}") from err

    if st.st_size > _MAX_SPEC_FILE_BYTES:
        maxsize = Human.bytesize(_MAX_SPEC_FILE_BYTES)
        raise Error(f"too large spec file '{specpath}', maximum allow size is {maxsize}")

    if not stat.S_ISREG(st.st_mode):
        raise Error(f"'{specpath}' is not a regular file")

    try:
        try:
            fobj = open(specpath, "r", encoding="utf-8") # pylint: disable=consider-using-with
        except OSError as err:
            msg = Error(str(err)).indent(2)
            raise Error(f"failed to open spec file '{specpath}:\n{msg}") from err

        loader = yaml.SafeLoader(fobj)
        event = None
        while True:
            event = loader.peek_event()
            if not event:
                raise Error("bad spec file '{specpath}': 'feature-id' key was not found")
            if isinstance(event, yaml.ScalarEvent):
                break
            loader.get_event()

        # The first 3 keys must be: name, desc, and feature-id.
        valid_keys = {"name", "desc", "feature-id"}
        left_keys = set(valid_keys)
        sdict = {}
        while len(sdict) < len(valid_keys):
            event = loader.get_event()
            if not event:
                keys = ", ".join(left_keys)
                raise Error(f"bad spec file '{specpath}': missing keys '{keys}'")

            key = str(event.value)
            if key not in valid_keys:
                raise Error(f"bad spec file '{specpath}' format: the first 3 keys must be "
                            f"'name', 'desc', and 'feature-id', got key '{key}' instead")
            if key in sdict:
                raise Error("bad spec file '{specpath}': repeating key '{key}'")

            event = loader.get_event()
            if not event:
                raise Error("bad spec file '{specpath}': no value for key '{key}'")

            if key == "feature-id":
                value = Trivial.str_to_int(event.value, what="'feature-id' key value")
            else:
                value = str(event.value)
            sdict[key] = value
            left_keys.remove(key)
    finally:
        if fobj:
            fobj.close()

    sdict["path"] = specpath
    return sdict

class Tpmi():
    """
    Provide API for reading and writing TPMI registers on Intel CPUs.
    """

    def _get_fdict(self, fname):
        """
        Return the feature dictionary feature 'fname'. If the dictionary is not available in the
        cache, loaded it from the spec file.
        """

        if fname in self._fdict_cache:
            return self._fdict_cache[fname]

        for specdir in self._specdirs:
            specpath = specdir / (fname + ".yaml")
            if specpath.exists():
                spec = YAML.load(specpath)

            self._fdict_cache[fname] = spec

        if fname not in self._fdict_cache:
            raise ErrorNotSupported("TPMI feature '{fname}' is not supported")

        return self._fdict_cache[fname]

    def list_features(self):
        """
        Detect the list of features supported by the target platform, scan the spec directories and
        detect the list of available spec files, and return a tuple of two lists:
        '(known_fnames, unknown_fids)'.
        The lists are as follows.
          * known - a list of spec dictionaries for every known feature (supported and have the spec
                    file).
          * unknown - a list of feature IDs for every unknown feature (supported, but no spec file
                      found).

        The spec dictionaries include the following keys.
          * name - feature name.
          * desc - feature description.
          * feature-id - an integer feature ID.
          * path - path to the spec file of the feature.
        """

        known = []
        for fname in self._fmap:
            known.append(self._sdicts[fname].copy())

        return known, sorted(self._unknown_fids)

    def _get_debugfs_tpmi_dirs(self):
        """
        Scan the debugfs root directory for TPMI-related sub-directories and return their paths in
        the form of a list.
        """

        debugfs_tpmi_dirs = []
        for dirname, path, _ in self._pman.lsdir(self._debugfs_mnt):
            if dirname.startswith("tpmi-"):
                debugfs_tpmi_dirs.append(path)

        if debugfs_tpmi_dirs:
            return debugfs_tpmi_dirs

        raise ErrorNotSupported(f"No TPMI-related sub-directories fount in '{self._debugfs_mnt}'"
                                f"{self._pman.hostmsg}.\nTPMI does not appear to be supported "
                                f"'{self._pman.hostmsg}. Here are the possible reasons:\n"
                                f" 1. Hardware does not support TPMI.\n"
                                f" 2. The kernel is old and doesn't have the TPMI driver. TPMI "
                                f" support was added in kernel version 6.6.\n"
                                f" 3. The TPMI driver is not enabled. Try to compile the kernel "
                                f"with 'CONFIG_INTEL_TPMI' enabled.\n")

    def _scan_spec_dirs(self):
        """
        Scan the spec directories, build spec dictionary for every known feature, and return a
        dictionary of spec dictionaries with keys being feature names.

        The dictionaries include basic feature information, such as name, feature ID and
        description.
        """

        sdicts = {}
        for specdir in self._specdirs:
            spec_files_cnt = 0
            non_yaml_cnt = 0
            load_errors_cnt = 0

            for specname in os.listdir(specdir):
                if not specname.endswith(".yml") and not specname.endswith(".yaml"):
                    non_yaml_cnt += 1
                    if non_yaml_cnt > _MAX_NON_YAML:
                        raise Error(f"too many non-YAML files in '{specdir}', maximum allowed "
                                    f"count is {_MAX_NON_YAML}")
                    continue

                try:
                    specpath = specdir / specname
                    sdict = _load_sdict(specpath)
                except Error as err:
                    load_errors_cnt += 1
                    if load_errors_cnt > _MAX_SCAN_LOAD_ERRORS:
                        raise Error(f"failed to load spec file '{specpath}':\n{err.indent(2)}\n"
                                    f"Reached the maximum spec file load errors count of "
                                    f"{_MAX_SCAN_LOAD_ERRORS}") from err
                    continue

                spec_files_cnt += 1
                if spec_files_cnt > _MAX_SPEC_FILES:
                    raise Error(f"too many spec files in '{specdir}, maximum allowed spec files "
                                f"count is {_MAX_SPEC_FILES}")

                sdicts[sdict["name"]] = sdict

        return sdicts

    def _build_features_map(self):
        """Build the TPMI feature map."""

        # A dictionary mapping feature IDs to debugfs paths corresponding to the feature.
        fid2paths = {}
        for pci_path in self._tpmi_pci_paths:
            for dirname, dirpath, _ in self._pman.lsdir(pci_path):
                match = re.match(r"^tpmi-id-([0-9a-f]+)$", dirname)
                if not match:
                    continue

                fid = int(match.group(1), 16)
                if fid not in fid2paths:
                    fid2paths[fid] = []

                fid2paths[fid].append(dirpath)

        if not fid2paths:
            paths = "\n * ".join([str(path) for path in self._tpmi_pci_paths])
            raise ErrorNotSupported(f"no TPMI features found{self._pman.hostmsg}, checked the "
                                    f"following paths:\n * {paths}")

        fmap = {}
        unknown_fids = []

        for fid, fpaths in fid2paths.items():
            fname = self._fid2fname.get(fid)
            if not fname:
                # Unknown feature, no spec file for it.
                unknown_fids.append(fid)
                continue

            if fname not in fmap:
                fmap[fname] = {}
            fmap[fname] = fpaths

        self._fmap = fmap
        self._unknown_fids = unknown_fids

    def __init__(self, pman, specdirs=None):
        """
        The class constructor. The arguments are as follows.
          * pman - the process manager object that defines the target host.
          * specdirs - a collection of spec directory paths on the target host to look for spec
                       files in (auto-detect by default).
        """

        self._specdirs = specdirs
        self._pman = pman

        # The feature dictionaries cache, indexed by feature name.
        self._fdict_cache = {}
        # The debugfs mount point.
        self._debugfs_mnt = None
        # Whether debugfs should be unmounted on 'close()'.
        self._unmount_debugfs = None
        # TPMI-related sub-directories in 'self._debugfs_mnt' (one per TPMI PCI device).
        self._tpmi_pci_paths = None
        # Spec files "sdict" dictionaries for every supported feature.
        self._sdicts = None
        # The feature ID -> feature name dictionary (supported features only).
        self._fid2fname = {}
        # The features map.
        self._fmap = None
        # Unknown feature IDs (no spec file).
        self._unknown_fids = None

        if not self._specdirs:
            self._specdirs = _find_spec_dirs()

        self._debugfs_mnt, self._unmount_debugfs = FSHelpers.mount_debugfs(pman=self._pman)
        self._tpmi_pci_paths = self._get_debugfs_tpmi_dirs()

        self._sdicts = self._scan_spec_dirs()
        for fname, sdict in self._sdicts.items():
            self._fid2fname[sdict["feature-id"]] = fname

        self._build_features_map()

    def close(self):
        """Uninitialize the class object."""

        if getattr(self, "_unmount_debugfs", None):
            with contextlib.suppress(Error):
                self._pman.run(f"unmount {self._debugfs_mnt}")

        ClassHelpers.close(self, unref_attrs=("_pman",))
