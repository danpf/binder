FROM ubuntu:20.04 as base

# General dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
	&& apt-get install -yq gnupg python3 python3-distutils python3-dev python3-pip ninja-build cmake git wget curl ccache \
	&& rm -rf /var/lib/apt/lists/* \
  && mkdir /binder

FROM base as prepared
# Config
ARG BINDER_BRANCH=""
ARG LLVM_VERSION=""
ARG PYBIND11_SHA=""
ARG BUILD_WITH_CCACHE=""

COPY ./cmake /binder/cmake
COPY ./source /binder/source
COPY ./build.py /binder/
COPY ./LICENSE /binder/

# COPY git remote get-url origin
RUN echo "\
 \n\
if [ -n \"$LLVM_VERSION\" ]; then BUILDCMDARGS=\" --llvm-version $LLVM_VERSION\"; else BUILDCMDARGS=\"\"; fi \n\
if [ -n \"$PYBIND11_SHA\" ]; then BUILDCMDARGS=\"\$BUILDCMDARGS --pybind11-sha $PYBIND11_SHA\"; fi \n\
if [ -n \"$BINDER_BRANCH\" ]; then BUILDCMDARGS=\"\$BUILDCMDARGS --binder-branch $BINDER_BRANCH\"; else BUILDCMDARGS=\"\$BUILDCMDARGS --binder-source /binder\"; fi \n\
if [ -n \"$BUILD_WITH_CCACHE\" ]; then BUILDCMDARGS=\"\$BUILDCMDARGS --build-with-ccache \"; fi \n\
if [ -z \"\$INSTALL\" ]; then BUILDCMDARGS=\"\$BUILDCMDARGS --prepare-only\"; fi \n\
if [ -n \"\$NCPUS\" ]; then BUILDCMDARGS=\"\$BUILDCMDARGS -j \$NCPUS\"; fi \n\
 \n\
python3 /binder/build.py --build-mode=Release --compiler gcc --build-path /build \$BUILDCMDARGS \$@ \n\
" >/binder/prepare_and_install_cmd.sh

FROM prepared as incremental-01
RUN cat /binder/prepare_and_install_cmd.sh && bash /binder/prepare_and_install_cmd.sh

FROM incremental-01 as final
ARG NCPUS=8
RUN cat /binder/prepare_and_install_cmd.sh && INSTALL=y NCPUS=$NCPUS bash /binder/prepare_and_install_cmd.sh --build-stages 1 && unset INSTALL NCPUS

# FROM incremental-02 as final
# ARG NCPUS=8
# RUN cat /binder/prepare_and_install_cmd.sh && INSTALL=y NCPUS=$NCPUS bash /binder/prepare_and_install_cmd.sh --build-stages 2 && unset INSTALL NCPUS
# COPY ./make_bindings_via_cmake.py /bin/

# FROM prepared AS final
# RUN INSTALL=y NCPUS=$NCPUS bash /binder/prepare_and_install_cmd.sh && unset INSTALL NCPUS
# If you want you should delete extra files here

FROM final AS test
COPY ./test /binder/test
RUN python3 /binder/build.py --run-tests --build-path /build --binder-source /binder
COPY ./examples /home/root/examples
RUN cd /home/root/examples \
  && make_bindings_via_cmake.py lbuild --output-directory bindings --module-name myexample --project-source ./example_struct/include --config-file ./example_struct/config.cfg --pybind11-source /build/pybind11
