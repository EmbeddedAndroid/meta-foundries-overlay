SUMMARY = "Factory image for Arduino UNO Q (QCS2290) with Foundries tooling"
LICENSE = "MIT"

# UNO Q is a memory-constrained 2GB part; we don't pull in the full
# qcom-multimedia-image stack (which is sized for RB3 Gen 2 / 6490).
# Start from core-image-base and add the Foundries product on top.
require recipes-core/images/core-image-base.bb
require recipes-samples/images/feature-fio.inc

IMAGE_FEATURES += "ssh-server-openssh"

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

# qcomflash IMAGE_FSTYPES is set globally by meta-qcom/ci/base.yml.
