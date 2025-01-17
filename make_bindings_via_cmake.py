#!/usr/bin/env python3

import importlib
import os
import sys
import shutil
import subprocess
from distutils.sysconfig import get_python_inc
from pathlib import Path
import argparse
from typing import List
import logging


log = logging.Logger(__name__)


def parseargs():
    def add_args(_parser: argparse.ArgumentParser, is_dbuild: bool):
        _parser.add_argument(
            "--output-directory", required=True, help="directory to build/output the cmake bindings and executables"
        )
        _parser.add_argument(
            "--module-name", required=True, help="what you would like to call this project (ie- import module-name)"
        )
        _parser.add_argument("--project-sources", nargs="+", required=True, help="the location of the project's source files")

        _parser.add_argument(
            "--source-directories-to-include",
            nargs="+",
            required=False,
            default=[],
            help="If you require any extra source directories to build your project, list them here",
        )

        _parser.add_argument("--config-file", required=True, help="A config file for you to use")
        _parser.add_argument(
            "--extra-binder-flags",
            default="",
            help="Extra binder flags, for debugging typically you use: --trace --annotate-includes",
        )
        _parser.add_argument(
            "--include-line-ignore-words",
            default=[],
            nargs="+",
            help="Ignore include lines that have any of these in them",
        )
        _parser.add_argument(
            "--preinstall-script",
            default="",
            help="Run this script before running binder",
        )

        _parser.add_argument(
            "--custom-all-includes-file",
            default="",
            help="custom all includes file path",
        )

        if not is_dbuild:
            _parser.add_argument(
                "--pybind11-source", required=True, help="the location of the pybind11 source directory"
            )
            _parser.add_argument(
                "--binder-executable", required=False, default="binder", help="Where binder is if not in $PATH"
            )
        else:
            _parser.add_argument(
                "--docker-image", required=False, default="binder", help="What docker image to use"
            )

    parser = argparse.ArgumentParser()
    master_parser = parser.add_subparsers(
        title="Subcommands", description="Valid subcommands", required=True, dest="subparser"
    )
    dbuild = master_parser.add_parser("dbuild")
    add_args(dbuild, is_dbuild=True)
    lbuild = master_parser.add_parser("lbuild")
    add_args(lbuild, is_dbuild=False)

    args = parser.parse_args()
    return args


def get_all_project_source_files(project_sources: List[str]) -> List[str]:
    all_source_files = []
    for project_source in project_sources:
        ps_pth = Path(project_source)
        lf = lambda x: list(ps_pth.rglob(x))
        all_source_files += lf("*.hpp") + lf("*.cpp") + lf("*.h") + lf("*.hh") + lf("*.cc") + lf("*.c")
    return [str(x) for x in all_source_files]


def make_and_write_all_includes(all_project_source_files: List[str], out_all_includes_fn: str, include_line_ignore_words: List[str]) -> None:
    all_includes = []
    for filename in all_project_source_files:
        with open(filename, "r") as fh:
            for line in fh:
                if line.startswith("#include") and not any(x in line for x in include_line_ignore_words):
                    line = line.strip()
                    # if '"' in line:
                    #     line = line.replace('"', "<")[:-1] + ">"
                    all_includes.append(line)
    all_includes = list(set(all_includes))
    # This is to ensure that the list is always the same and doesn't
    # depend on the filesystem state.  Not technically necessary, but
    # will cause inconsistent errors without it.
    all_includes.sort()
    with open(out_all_includes_fn, "w") as fh:
        for include in all_includes:
            fh.write(f"{include}\n")


def make_bindings_code(
    binder_executable: str,
    all_includes_fn: str,
    bindings_dir: str,
    python_module_name: str,
    extra_source_directories: List[str],
    extra_binder_flags: str,
    config_file: str,
):
    includes = " ".join([f"-I{x}" for x in extra_source_directories])
    command = (
        f"{binder_executable} --root-module {python_module_name}"
        f" --prefix {bindings_dir} {extra_binder_flags}"
        f" --config {config_file}"
        f" {all_includes_fn} -- -std=c++11"
        f" {includes} -DNDEBUG -v"
    )
    print("running command", command)
    ret = subprocess.run(command.split())
    if ret.returncode != 0:
        raise RuntimeError(f"Bad command return {command}")
    sources_to_compile = []
    with open(os.path.join(bindings_dir, f"{python_module_name}.sources"), "r") as fh:
        for line in fh:
            l = line.strip()
            if l in sources_to_compile:
                raise RuntimeError(
                    "WARNING - DUPLICATED SOURCE - DO NOT NAME YOUR MODULE THE SAME AS ONE OF YOUR NAMESPACES/CLASSES"
                )
            sources_to_compile.append(l)
    return sources_to_compile


def compile_sources(
    sources_to_compile: List[str],
    bindings_dir: str,
    module_name: str,
    directories_to_include: List[str],
    pybind11_source: str,
    all_project_source_files: List[str],
):
    lines_to_write = []
    lines_to_write.append(f"cmake_minimum_required(VERSION 3.4...3.18)")
    lines_to_write.append(f"project({module_name})")
    lines_to_write.append(f'add_subdirectory("{pybind11_source}" "${{CMAKE_CURRENT_BINARY_DIR}}/pybind11_build")')
    lines_to_write.append("")
    # lines_to_write.append(f"add_subdirectory(\"{pybind11" "${CMAKE_CURRENT_BINARY_DIR}/testlib_build"))
    tolink = []
    for source_fn in all_project_source_files:
        if "c" in Path(source_fn).suffix:
            source_lib_name = str(source_fn).replace("/", "_").replace(".", "_")
            lines_to_write.append(f"add_library({source_lib_name} STATIC ${{CMAKE_SOURCE_DIR}}/{source_fn})")
            lines_to_write.append(f"set_target_properties({source_lib_name} PROPERTIES POSITION_INDEPENDENT_CODE ON)")
            lines_to_write.append(
                f"target_include_directories({source_lib_name} PRIVATE {' '.join(directories_to_include)})"
            )
            tolink.append(source_lib_name)

    sources_to_compile_for_cmake = ["${CMAKE_CURRENT_BINARY_DIR}/" + x for x in sources_to_compile]
    lines_to_write.append(f"pybind11_add_module({module_name} MODULE {' '.join(sources_to_compile_for_cmake)})")
    lines_to_write.append(f"target_include_directories({module_name} PRIVATE {' '.join(directories_to_include)})")
    lines_to_write.append(f"set_target_properties({module_name} PROPERTIES POSITION_INDEPENDENT_CODE ON)")

    lines_to_write.append(f"target_link_libraries({module_name} PRIVATE {' '.join(tolink)})")

    with open("CMakeLists.txt", "w") as f:
        for line in lines_to_write:
            f.write(f"{line}\n")

    # Done making CMakeLists.txt
    subprocess.run("cmake -G Ninja -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_C_COMPILER=clang ..".split(), cwd=bindings_dir)
    subprocess.run("ninja -v".split(), cwd=bindings_dir)
    if bindings_dir not in sys.path:
        sys.path.append(bindings_dir)

    sys.stdout.flush()
    print("Testing Python lib...")
    new_module = importlib.import_module(module_name)
    print(dir(new_module))
    print(new_module)


def validate_args(args: argparse.Namespace):
    if getattr(args, "binder_executable", None) is None and args.subparser == "lbuild":
        new_binder = shutil.which("binder")
        if new_binder is None:
            raise RuntimeError("Unable to find binder in $PATH")


def run_in_docker(docker_image: str):
    new_args = []
    for i, x in enumerate(sys.argv[1:]):
        if x == "dbuild":
            new_args.append("lbuild")
        if "docker-image" in x or (i > 0 and "docker-image" in sys.argv[1:][i-1]):
            continue
        new_args.append(x)
    command = [
        "docker",
        "run",
        "--workdir",
        os.getcwd(),
        "-v",
        f"{os.getcwd()}:{os.getcwd()}",
        "-t",
        docker_image,
        "make_bindings_via_cmake.py",
        *new_args,
    ]
    command += ["--pybind11-source", "/build/pybind11", "--binder-executable", "binder"]
    log.info(" ".join(command))
    log.debug(" ".join(command))
    log.warning(" ".join(command))
    # log.error(" ".join(command))
    ret = subprocess.run(command)
    if ret.returncode:
        raise RuntimeError(f"Error with command: {' '.join(command)}")


def run_preinstall_script(preinstall_script: str):
    if preinstall_script:
        subprocess.run(["sh", preinstall_script])

def main():
    args = parseargs()
    if args.subparser == "dbuild":
        run_in_docker(args.docker_image)
        return
    else:
        validate_args(args)
    run_preinstall_script(args.preinstall_script)

    extra_source_directories = [
        *args.project_sources,
        get_python_inc(),
        "pybind11/include",
    ] + args.source_directories_to_include
    extra_source_directories = [str(Path(x).resolve()) for x in extra_source_directories]

    shutil.rmtree(args.output_directory, ignore_errors=True)
    Path(args.output_directory).mkdir(exist_ok=True, parents=True)
    all_project_source_files = get_all_project_source_files(args.project_sources)

    if args.custom_all_includes_file:
        all_includes_fn = str(Path(args.custom_all_includes_file).resolve())
    else:
        all_includes_fn = str((Path(args.output_directory) / "all_includes.hpp").resolve())
        make_and_write_all_includes(all_project_source_files, all_includes_fn, args.include_line_ignore_words)


    sources_to_compile = make_bindings_code(
        args.binder_executable,
        all_includes_fn,
        args.output_directory,
        args.module_name,
        extra_source_directories,
        args.extra_binder_flags,
        args.config_file,
    )
    compile_sources(
        sources_to_compile,
        args.output_directory,
        args.module_name,
        extra_source_directories,
        args.pybind11_source,
        all_project_source_files,
    )


if __name__ == "__main__":
    main()
