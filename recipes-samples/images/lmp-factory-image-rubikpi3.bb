SUMMARY = "Factory image for Thundercomm RUBIK Pi 3 (QCS6490) with Foundries tooling"
LICENSE = "MIT"

# Extend qcom-multimedia-image like factory-rb3gen2 does. RUBIK Pi 3 has
# 4-8 GB RAM (depending on SKU) so the full multimedia stack — wayland,
# weston, gstreamer, pipewire, libcamera — is the right baseline. That
# matches what the cam-detect + marketplace demo flow needs on the board
# (Wayland for the live frame feed, gstreamer for the cam pipeline) and
# gives us the same NetworkManager / fstab / ESP-mount machinery
# rb3gen2 gets through qcom-distro-sota.
require recipes-products/images/qcom-multimedia-image.bb
require recipes-samples/images/feature-fio.inc

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

# Dragonwing marketplace stack + cam-test scaffolds + firstboot
# orchestrator. Pulled in from EmbeddedAndroid/meta-qcom-3rdparty's
# rubrikpi3-next branch and re-homed into this overlay under
# dynamic-layers/qcom/recipes-extended/. The cam-detect Docker image
# is built on first boot by dragonwing-firstboot (uses Docker + the
# rubikpi3-cam-test-src sources baked into /root/cam-test/).
IMAGE_INSTALL:append = " \
    dragonwing-marketplace \
    dragonwing-firstboot \
    dragonwing-apps \
    dragonwing-qai-export \
    rubikpi3-cam-test-src \
"
