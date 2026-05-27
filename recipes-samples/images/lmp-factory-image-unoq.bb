SUMMARY = "Factory image for Arduino UNO Q (QCS2290) with Foundries tooling"
LICENSE = "MIT"

# Start from qcom-console-image (the lightweight qcom-distro base that
# qcom-multimedia-image extends) so we inherit the proper UKI/ESP/fstab
# boot integration and qcom-distro userspace stack: NetworkManager-wifi
# via the meta-package RRECOMMENDS chain, the qcom-utilities
# packagegroups, systemd-networkd opted out via BAD_RECOMMENDATIONS,
# kernel-modules, resize-rootfs, ssh-server-openssh, etc. The full
# qcom-multimedia-image stack (wayland/weston/gstreamer/pipewire) is
# too heavy for UNO Q's 2 GB RAM, but qcom-console-image is sized for
# a console-only board.
require recipes-products/images/qcom-console-image.bb
require recipes-samples/images/feature-fio.inc

CORE_IMAGE_BASE_INSTALL += "docker-cli-config"
