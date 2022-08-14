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
COPY ./make_bindings_via_cmake.py /bin/
COPY docker/ccache* /home/root/.ccache

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
python3 /binder/build.py --build-mode=Release --compiler gcc --build-path /build \$BUILDCMDARGS \n\
" >/binder/prepare_and_install_cmd.sh

RUN cat /binder/prepare_and_install_cmd.sh && bash /binder/prepare_and_install_cmd.sh

FROM prepared AS final
ARG NCPUS=8
RUN INSTALL=y NCPUS=$NCPUS bash /binder/prepare_and_install_cmd.sh && unset INSTALL NCPUS
# If you want you should delete extra files here

FROM final AS test
COPY ./test /binder/test
RUN python3 /binder/build.py --run-tests xx --build-path /build --binder-source /binder
