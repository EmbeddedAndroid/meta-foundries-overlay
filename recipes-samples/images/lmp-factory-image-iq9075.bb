SUMMARY = "Factory image for Qualcomm IQ-9075 EVK (QCS9075 / sa8775p) with Foundries tooling"
LICENSE = "MIT"

# qcom-multimedia-image base (wayland/weston/gstreamer + the qcom-distro
# userspace stack: NetworkManager-wifi, qcom-utilities packagegroups,
# kernel-modules, resize-rootfs, ssh-server-openssh) plus the proper
# UKI/ESP/fstab boot integration. Same base as the VENTUNO Q factory image --
# the weston stack is required by the Dragonwing kiosk desktop below.
require recipes-products/images/qcom-multimedia-image.bb
require recipes-samples/images/feature-fio.inc

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

# The IQ-9075 EVK boot firmware (firmware-qcom-boot-qcs9100, pulled via the
# machine's QCOM_BOOT_FIRMWARE) ships under the restricted LICENSE.qcom-2.
# Accept it so the qcomflash boot set can be deployed. Mirrors the ventuno-q
# exception; scoped here because we build our own image.
INCOMPATIBLE_LICENSE_EXCEPTIONS:append:iq-9075-evk = " firmware-qcom-boot-qcs9100:LICENSE.qcom-2"

# NPU/DSP stack is pulled by the iq-9075-evk machine config
# (MACHINE_ESSENTIAL_EXTRA_RRECOMMENDS: packagegroup-iq-9075-evk-firmware,
# packagegroup-iq-9075-evk-hexagon-dsp-binaries, qairt-sdk-hexagon-v73).
# No image-level add needed for the DSP-side skels.

# Host-side QNN/QAIRT runtime for NPU (Hexagon HTP) inference: provides
# libQnnTFLiteDelegate.so, libQnnHtp.so + V73 stub, qnn-net-run, SNPE. The
# machine config already pulls qairt-sdk-hexagon-v73 (the signed DSP-side
# skels); without the host runtime the TFLite HTP external delegate cannot
# load. (~200 MB; revisit slimming later.)
IMAGE_INSTALL:append = " qairt-sdk"

# Dragonwing marketplace stack (:8080 agentic app dashboard) + NPU cam-test
# demo — identical userspace to VENTUNO Q. Framework recipes are allarch and
# shared across boards; the cam-test NPU base uses the V73 variant
# (iq9075-cam-test-src), matching qairt-sdk-hexagon-v73 in this image.
IMAGE_INSTALL:append = " \
    dragonwing-marketplace \
    dragonwing-firstboot \
    dragonwing-apps \
    dragonwing-qai-export \
    iq9075-cam-test-src \
"

# /usr/lib/dsp compat symlink for the multi-SoC DSP runtime layout, so the
# marketplace's -v /usr/lib/dsp bind-mount + ADSP_LIBRARY_PATH resolve.
require recipes-samples/images/dsp-compat.inc

# Dragonwing Weston kiosk desktop UI (wallpaper, Marketplace launcher, kiosk).
require recipes-samples/images/dragonwing-desktop.inc
