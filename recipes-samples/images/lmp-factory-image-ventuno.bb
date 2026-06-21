SUMMARY = "Factory image for Arduino VENTUNO Q (monza / QCS8275) with Foundries tooling"
LICENSE = "MIT"

# Start from qcom-console-image (the lightweight qcom-distro base that
# qcom-multimedia-image extends) so we inherit the proper UKI/ESP/fstab
# boot integration and qcom-distro userspace stack: NetworkManager-wifi
# via the meta-package RRECOMMENDS chain, the qcom-utilities
# packagegroups, kernel-modules, resize-rootfs, ssh-server-openssh, etc.
# VENTUNO Q (QCS8275) has plenty of RAM for the full qcom-multimedia
# stack, but we mirror the UNO Q console base for a low-risk first
# bring-up; switch the require to qcom-multimedia-image.bb later if the
# wayland/weston/gstreamer stack is wanted.
require recipes-products/images/qcom-multimedia-image.bb
require recipes-samples/images/feature-fio.inc

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

# VENTUNO Q's boot firmware (firmware-qcom-boot-qcs8275-arduino-monza)
# ships under the restricted LICENSE.qcom-2. Accept it so the qcomflash
# boot set can be deployed. Mirrors the upstream qcom-multimedia-image
# bbappend exception; scoped here because we build our own image.
INCOMPATIBLE_LICENSE_EXCEPTIONS:append:ventuno-q = " firmware-qcom-boot-qcs8275-arduino-monza:LICENSE.qcom-2"

# NPU/DSP stack (hexagon-dsp-binaries + qairt-sdk-hexagon-v75) is pulled
# by the ventuno-q machine config (MACHINE_EXTRA_RRECOMMENDS), same as the
# upstream qcs8300-ride/sa8775p-ride packagegroups. No image-level add needed.

# Host-side QNN/QAIRT runtime for NPU (Hexagon HTP) inference: provides
# libQnnTFLiteDelegate.so, libQnnHtp.so + V75 stub, qnn-net-run, SNPE. The
# machine config already pulls qairt-sdk-hexagon-v75 (the signed DSP-side
# skels for QCS8300); without the host runtime the TFLite HTP external
# delegate cannot load. (~200 MB; revisit slimming later.)
IMAGE_INSTALL:append = " qairt-sdk"

# Dragonwing marketplace stack (:8080 agentic app dashboard) + NPU cam-test
# demo. Framework recipes are allarch and shared with rubikpi3; the cam-test
# NPU base uses the V75 variant (ventuno-cam-test-src) built against QAIRT
# 2.43 Hexagon V75 host stubs, matching qairt-sdk-hexagon-v75 in this image.
IMAGE_INSTALL:append = " \
    dragonwing-marketplace \
    dragonwing-firstboot \
    dragonwing-apps \
    dragonwing-qai-export \
    ventuno-cam-test-src \
"
