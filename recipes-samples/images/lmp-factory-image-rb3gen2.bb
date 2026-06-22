SUMMARY = "Factory image for Qualcomm RB3 Gen 2 (QCS6490) with Foundries tooling"
LICENSE = "MIT"

# RB3 Gen 2 (qcm6490) shares the QCS6490 SoC + Hexagon V68 cDSP with the
# RUBIK Pi 3, so the same qcom-multimedia base and the same V68 Dragonwing
# marketplace + cam-test stack apply unchanged. The cam-test NPU base
# (rubikpi3-cam-test-src) is COMPATIBLE_MACHINE-widened to rb3gen2-core-kit.
require recipes-products/images/qcom-multimedia-image.bb
require recipes-samples/images/feature-fio.inc

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

IMAGE_INSTALL:append = " \
    dragonwing-marketplace \
    dragonwing-firstboot \
    dragonwing-apps \
    dragonwing-qai-export \
    rubikpi3-cam-test-src \
"

# /usr/lib/dsp compat symlink for the multi-SoC DSP runtime layout.
require recipes-samples/images/dsp-compat.inc
