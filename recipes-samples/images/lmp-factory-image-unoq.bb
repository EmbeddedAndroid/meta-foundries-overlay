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

# EDK2 firmware on UNO Q boots the Unified Kernel Image directly without
# routing through systemd-boot, so it never sets the
# LoaderDevicePartUUID EFI variable. systemd-gpt-auto-generator then
# can't identify the ESP and skips auto-mounting it at /boot, which
# blocks libostree (no BLS entries visible -> aklite deploy fails).
# Mount the ESP explicitly via /etc/fstab. This is UNO Q-specific:
# rb3gen2 + intel boot through systemd-boot and don't need the
# workaround. Drop this once EDK2 boots BOOTAA64 first and
# LoaderDevicePartUUID is populated correctly.
unoq_fstab_boot () {
    cat >> ${IMAGE_ROOTFS}/etc/fstab <<'EOF'

# Mount the ESP at /boot so libostree can read BLS entries from
# /boot/loader/entries/. Workaround for EDK2 not setting
# LoaderDevicePartUUID on this board.
PARTLABEL=efi   /boot   vfat   defaults,errors=remount-ro   0 2
EOF
}

ROOTFS_POSTPROCESS_COMMAND += "unoq_fstab_boot;"
