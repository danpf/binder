#!/usr/bin/env python
# -*- coding: utf-8 -*-
# :noTabs=true:

# (c) Copyright Rosetta Commons Member Institutions.
# (c) This file is part of the Rosetta software suite and is made available under license.
# (c) The Rosetta software is developed by the contributing members of the Rosetta Commons.
# (c) For more information, see http://www.rosettacommons.org. Questions about this can be
# (c) addressed to University of Washington CoMotion, email: license@uw.edu.

## @file   build.py
## @brief  Script to build Binder
## @author Danny Farrell

from typing import List
import sys
import argparse
import subprocess
import shutil
from abc import ABCMeta, abstractmethod
from pathlib import Path


def get_platform():
    if sys.platform.startswith("linux"):
        platform = "linux"  # can be linux1, linux2, etc
    else:
        known_platforms = {"darwin": "macos", "cygwin": "cygwin", "win32": "windows"}
        platform = known_platforms.get(sys.platform, "unknown")
    return platform


SUPPORTED_PYBIND11_SHA = "32c4d7e17f267e10e71138a78d559b1eef17c909"
ALLOWED_BUILD_MODES = ("Release", "Debug", "MinSizeRel", "RelWithDebInfo")
KNOWN_COMPILERS = {
    "clang": ["clang", "clang++"],
    "gcc": ["gcc", "g++"],
}

SUGGESTED_LLVM_RELEASE = "llvmorg-13.0.1"
SUGGESTED_BINDER_BRANCH = "master"


class CompileOptions:
    _cmake_cc_compiler_template = "-DCMAKE_C_COMPILER={}"
    _cmake_cxx_compiler_template = "-DCMAKE_CXX_COMPILER={}"
    _cmake_build_mode_compiler_template = "-DCMAKE_BUILD_TYPE={}"

    _allowed_build_modes = ALLOWED_BUILD_MODES
    _compiler_map = KNOWN_COMPILERS

    def __init__(self, compiler: str, build_mode: str):
        if build_mode not in self._allowed_build_modes:
            raise RuntimeError(f"Build mode {build_mode} not supported, we support {self._allowed_build_modes}")
        self.build_mode = build_mode
        if compiler not in self._compiler_map:
            raise RuntimeError(f"Compiler {compiler} not supported, we support {self._compiler_map.keys()}")
        self.compiler = compiler
        self.cc, self.cpp = self._compiler_map[compiler]
        self.cmake_extra_commands = self.cmake_extra_commands_from_known_compiler_paths(
            full_cc=self.cc, full_cpp=self.cpp, build_mode=self.build_mode
        )

    @classmethod
    def cmake_extra_commands_from_known_compiler_paths(cls, full_cc: str, full_cpp: str, build_mode: str) -> str:
        out = []
        if full_cc:
            out.append(cls._cmake_cc_compiler_template.format(full_cc))
        if full_cpp:
            out.append(cls._cmake_cxx_compiler_template.format(full_cpp))
        if build_mode:
            out.append(cls._cmake_build_mode_compiler_template.format(build_mode))
        return " ".join(out)


class VersionOrSourceLocation:
    def __init__(self, version: str = "", source_location: str = ""):
        if version and source_location:
            raise RuntimeError(
                f"Must have only version OR source_location, not both -- have version='{version}', source_location='{source_location}'"
            )
        if not version and not source_location:
            raise RuntimeError(
                f"Must have only version OR source_location, not neither -- have version='{version}', source_location='{source_location}'"
            )
        self.version = version
        self.source_location = source_location

    def get_id(self):
        if self.version:
            return self.version
        else:
            return f"FROM_SOURCE_{self.source_location}"


class BaseInstaller(metaclass=ABCMeta):
    @abstractmethod
    def _prepare(self):
        """Setup the directories + download the packages"""
        pass

    def prepare(self):
        """Setup the directories + download the packages"""
        self._prepare()

    @abstractmethod
    def _install(self):
        """Setup the directories + download the packages + install them"""

        pass

    def install(self):
        """Setup the directories + download the packages + install them"""
        self._prepare()
        self._install()


class MasterBinderInstaller(BaseInstaller):
    _git_remote = "https://github.com/RosettaCommons/binder.git"
    """
    Generally you install binder with the following format:
        /build/
        ├─ binder/
        ├─ llvm/
        │  ├─ clang/
        │  │  ├─ build/
        │  │  │  ├─ bin/ (binaries in here)
        │  ├─ bin/ (our symlink to clang/build/bin)
        │  ├─ clang-tools-extra/
        │  ├─ VERSION
        │  ├─ ...
        ├─ pybind11/
        │  ├─ include/
        │  ├─ ...
        ├─ ENVFILE

    **NOTE: This is NOT setup to build binder's tests, only binder.
    """

    def __init__(
        self,
        binder_branch_or_source_location: VersionOrSourceLocation,
        llvm_version_or_source_location: VersionOrSourceLocation,
        pybind11_sha_or_source_location: VersionOrSourceLocation,
        build_dir: str,
        _compiler: str,
        build_mode: str,
        install_cpus: int,
    ):
        self.llvm_version_or_source_location = llvm_version_or_source_location
        self.pybind11_sha_or_source_location = pybind11_sha_or_source_location
        self.binder_branch_or_source_location = binder_branch_or_source_location
        self.compiler = CompileOptions(_compiler, build_mode)
        self.build_dir = build_dir
        self.install_cpus = install_cpus

        self.binder_download_dir = str(Path(self.build_dir) / "binder")
        binder_source_directory = (
            str(Path(self.binder_download_dir) / "source")
            if self.binder_branch_or_source_location.version
            else str(Path(self.binder_branch_or_source_location.source_location) / "source")
        )

        self.llvm_installer = LLVMInstall(
            llvm_version_or_source_location,
            self.compiler,
            binder_source_directory,
            base_source_directory=str(Path(self.build_dir) / "llvm-project"),
            install_cpus=self.install_cpus,
        )
        self.pybind11_installer = Pybind11Installer(pybind11_sha_or_source_location, str(Path(build_dir) / "pybind11"))
        self.envfile = str(Path(build_dir) / "ENVFILE")

    def _prepare(self):
        if self.binder_branch_or_source_location.version:
            download_command = f"git clone --depth 1 --branch {self.binder_branch_or_source_location.version} {self._git_remote} {self.binder_download_dir}"
            ret = subprocess.run(download_command.split())
            if ret.returncode != 0:
                raise RuntimeError(f"Error downloading binder version {self.binder_branch_or_source_location.version}")
        self.pybind11_installer.prepare()
        self.llvm_installer.prepare()

    def _install(self):
        env_info = []
        env_info += self.pybind11_installer._install()
        env_info += self.llvm_installer._install()
        with open(self.envfile, "w") as fh:
            fh.write("\n".join(env_info))


class LLVMInstall(BaseInstaller):
    _binder_clang_tools_extras_subdir = "binder"
    _git_remote = "https://github.com/llvm/llvm-project.git"
    """
    Generally you install binder with the following format:
        /build/
        ├─ binder/
        ├─ llvm/
        │  ├─ clang/
        │  │  ├─ build/
        │  │  │  ├─ bin/ (binaries in here)
        │  ├─ bin/ (our symlink to clang/build/bin)
        │  ├─ clang-tools-extra/
        │  ├─ VERSION
        │  ├─ ...
        ├─ pybind11/
        │  ├─ include/
        │  ├─ ...
        ├─ ENVFILE

    This class sets help setup the clang/llvm part of that relationship for you,
    gets you ready to install llvm/clang, and gives you access to the files/dirs you might
    need to use to build binder.

    In the above example:
        /build is our 'base_install_directory'
        /build/llvm is our 'build_subdir'
    """

    def __init__(
        self,
        version_or_source_location: VersionOrSourceLocation,
        _compiler: CompileOptions,
        binder_source_directory: str,
        base_source_directory: str = "/build/llvm-project",
        build_subdir: str = "build",
        install_cpus: int = 8,

    ):
        self.version_or_source_location = version_or_source_location
        self.base_source_directory = base_source_directory
        self.binder_source_directory = binder_source_directory
        self.build_subdir = build_subdir
        self.compiler = _compiler
        self.install_cpus = install_cpus

        basedir = Path(self.base_source_directory)
        self.build_dir = str(Path(self.base_source_directory) / build_subdir)
        self.build_bin_dir = str(Path(self.build_dir) / "bin")
        self.llvm_dir = str(Path(self.base_source_directory) / "llvm")

        self.clang_tools_extra_subdir = str(basedir / "clang-tools-extra")
        self.clang_tools_extra_subdir_cmakelists = str(Path(self.clang_tools_extra_subdir) / "CMakeLists.txt")
        self.binder_clang_tools_extra_subdir = str(
            Path(self.clang_tools_extra_subdir) / self._binder_clang_tools_extras_subdir
        )

    def _run_llvm_cmake_base_command(self, cmake_extra_commands: str):
        command = (
            f"cmake llvm -B {self.build_dir} -G Ninja"
            f" {cmake_extra_commands}"
            f" -DLLVM_ENABLE_LIBCXX=ON -DLLVM_INCLUDE_TESTS=OFF -DLLVM_ENABLE_RUNTIMES='libc;libcxx;libcxxabi' -DLLVM_ENABLE_PROJECTS='clang-tools-extra;clang' -DLLVM_ENABLE_EH=1 -DLLVM_ENABLE_RTTI=ON"
        )
        print("Running command", command)
        ret = subprocess.run(command.split(), cwd=self.base_source_directory)
        if ret.returncode != 0:
            raise RuntimeError("Error running llvm cmake init command")

    def _run_ninja_build_and_install_command(self):
        for command in [
            f"ninja -j {self.install_cpus}",
            f"ninja install-clang-resource-headers install-cxx install-cxxabi install-clang tools/clang/tools/extra/binder/install install-clang-headers  -j {self.install_cpus}",
        ]:
            # install-libc install-libcxx install-libcxxabi
            print("Running command", command)
            ret = subprocess.run(command.split(), cwd=self.build_dir)
            if ret.returncode != 0:
                raise RuntimeError("Error running llvm build command")

    def _setup_ldconfig_path(self):
        base_ldconfig_path = "/etc/ld.so.conf.d"
        out_ld_fn = "libc2.conf"
        Path(base_ldconfig_path).mkdir(exist_ok=True,parents=True)
        with open(str(Path(base_ldconfig_path)/out_ld_fn), "w") as fh:
            fh.write("/usr/local/lib/x86_64-unknown-linux-gnu")
        command = "ldconfig"
        print("Running command", command)
        ret = subprocess.run([command], cwd=self.build_dir)
        if ret.returncode != 0:
            raise RuntimeError("Error running llvm build command")

    def _prepare(self):
        if not Path(self.binder_source_directory).is_dir():
            raise RuntimeError(
                "Cannot install llvm without binder, unable to find binder source at {self.binder_source_subdir}"
            )
        if not Path(self.base_source_directory).is_dir():
            if self.version_or_source_location.source_location:
                shutil.copytree(self.version_or_source_location.source_location, self.base_source_directory)
            else:
                download_command = f"git clone --depth 1 --branch {self.version_or_source_location.version} {self._git_remote} {self.base_source_directory}"
                # download_command = f"git clone --depth 1 {self._git_remote} {self.base_source_directory}"
                ret = subprocess.run(download_command.split())
                if ret.returncode != 0:
                    raise RuntimeError("Error downloading llvm")

            shutil.copytree(self.binder_source_directory, self.binder_clang_tools_extra_subdir)
            with open(self.clang_tools_extra_subdir_cmakelists, "a") as fh:
                fh.write(f"\nadd_subdirectory({self._binder_clang_tools_extras_subdir})\n")

    def _install(self) -> List[str]:
        # 1. Run cmake and build the first time, use the system compiler.
        self._run_llvm_cmake_base_command(self.compiler.cmake_extra_commands)
        self._run_ninja_build_and_install_command()
        self._setup_ldconfig_path()
        # 2. Run cmake and build the second time, but this time use the clang
        #    that we just built.  Do not use the clang C because it won't work
        #    because you will fail with `Test LLVM_LIBSTDCXX_MIN - Failed`
        self.build_dir = self.build_dir + "2"
        # I'm not sure but i think it helps to use the clang after it's installed
        # in the system.
        # clangpp_bin = str((Path(self.build_bin_dir) / "clang++").resolve())
        # clang_bin = str((Path(self.build_bin_dir) / "clang").resolve())
        self._run_llvm_cmake_base_command(
            CompileOptions.cmake_extra_commands_from_known_compiler_paths("clang", "clang++", self.compiler.build_mode)
        )
        self._run_ninja_build_and_install_command()
        return ["LLVM_BIN_DIR={self.build_bin_dir}", "LLVM_VERSION={self.version}"]


class Pybind11Installer(BaseInstaller):
    _git_remote = "https://github.com/RosettaCommons/pybind11.git"

    def __init__(
        self, github_sha_or_source_location: VersionOrSourceLocation, base_source_directory: str = "/build/pybind11",
    ):
        self.github_sha_or_source_location = github_sha_or_source_location
        self.base_source_directory = base_source_directory
        self.include_dir = str(Path(self.base_source_directory) / "include")

    def _prepare(self):
        if not Path(self.include_dir).is_dir():
            if self.github_sha_or_source_location.source_location:
                shutil.copytree(self.github_sha_or_source_location.source_location, self.base_source_directory)
            else:
                Path(self.base_source_directory).mkdir(exist_ok=True, parents=True)
                for command in [
                    "git init",
                    f"git remote add origin {self._git_remote}",
                    f"git fetch --depth 1 origin {self.github_sha_or_source_location.version}",
                    "git checkout FETCH_HEAD",
                ]:
                    print("Running command:", command)
                    ret = subprocess.run(command.split(), cwd=self.base_source_directory)
                    if ret.returncode != 0:
                        raise RuntimeError("Error downloading pybind11")

            if not Path(self.include_dir).exists():
                raise RuntimeError(f"Error downloading pybind11, unable to find path {self.include_dir}")

    def _install(self) -> List[str]:
        # no install necessary
        return [
            f"PYBIND11_INCLUDE_DIR={self.include_dir}",
            f"PYBIND11_SHA={self.github_sha_or_source_location.get_id()}",
        ]


def parse_args(args: List[str]):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-j",
        "--jobs",
        default=1,
        type=int,
        help="Number of processors to use on when building, 0 = infer from # cpus on this computer (default: 1) ",
    )
    parser.add_argument(
        "--build-mode", default="Release", choices=ALLOWED_BUILD_MODES, help="Specify build mode",
    )
    parser.add_argument(
        "--compiler",
        default="clang",
        choices=tuple(KNOWN_COMPILERS.keys()),
        help="Compiler to use for the INITIAL build. This is eventually replaced with the built clang",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        default=False,
        help="Prepare to install binder, but don't actually try to install it.",
    )

    parser.add_argument("--build-path", required=True, help="Output directory to install binder, and it's dependencies")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pybind11-sha", default=SUPPORTED_PYBIND11_SHA, help=f"Path to pybind11 source tree.")
    group.add_argument(
        "--pybind11-source",
        help="Path to pybind11 source tree, if none is given then it will download based on the default RosettaCommons sha",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--llvm-source",
        default="",
        help="Path to llvm source tree, if none is given then it will download based on --llvm-version",
    )
    group.add_argument("--llvm-version", default=SUGGESTED_LLVM_RELEASE, help=f"llvm version to build with.")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--binder-source", default="", help="Path to binder source (not the dir 'source', the entire binder directory)"
    )
    group.add_argument(
        "--binder-branch", default="", help=f"Binder branch to use. -- default to use is {SUGGESTED_BINDER_BRANCH}"
    )

    parser.add_argument("--pybind11-git-url", help="git url for pybind11")
    parser.add_argument("--binder-git-url", help="git url for binder")
    parser.add_argument("--llvm-git-url", help="git url for llvm")

    options = parser.parse_args(args)
    if options.jobs == 0:
        import multiprocessing

        options.jobs = multiprocessing.cpu_count()
    return options


def main(args: argparse.Namespace):
    """Binding demo build/test script"""
    if args.pybind11_git_url:
        Pybind11Installer._git_remote = args.pybind11_git_url
    if args.binder_git_url:
        MasterBinderInstaller._git_remote = args.binder_git_url
    if args.llvm_git_url:
        LLVMInstall._git_remote = args.llvm_git_url

    pybind11_sha_or_source_location = VersionOrSourceLocation(args.pybind11_sha, args.pybind11_source)
    llvm_version_or_source_location = VersionOrSourceLocation(args.llvm_version, args.llvm_source)
    binder_branch_or_source_location = VersionOrSourceLocation(args.binder_branch, args.binder_source)
    mbi = MasterBinderInstaller(
        binder_branch_or_source_location,
        llvm_version_or_source_location,
        pybind11_sha_or_source_location,
        args.build_path,
        args.compiler,
        args.build_mode,
        install_cpus=args.jobs,
    )
    if args.prepare_only:
        mbi.prepare()
    else:
        mbi.install()


if __name__ == "__main__":
    main(parse_args(sys.argv[1:]))
