# In-flight kernel changes for UNO Q (Arduino UNO Q / QCS2290 / imola).
#
# Two pieces:
#
#  1. block-as-nvmem v2 patch series (Loic Poulain, oss.qualcomm.com,
#     2026-05-07). Adds NVMEM-provider semantics to MMC + ath10k + qca
#     Bluetooth, and the arduino-imola DTS that consumes them. Required
#     for stable WLAN/BT MAC addresses on UNO Q. Submitted upstream.
#     https://lore.kernel.org/all/20260507-block-as-nvmem-v2-0-bf17edd5134e@oss.qualcomm.com/
#
#  2. arduino.config kconfig fragment. Pulled verbatim from
#     github.com/arduino/arduino-deb-images@kernel-configs/arduino.config.
#     UNO Q userspace stack (audio, BT, exFAT, ANX bridge, ZRAM/ZSWAP)
#     expects these knobs set.
#
# Drop both as a unit once block-as-nvmem v2 lands in qcom-next and the
# arduino config knobs make it into meta-qcom's bsp-additions.cfg.

FILESEXTRAPATHS:prepend:uno-q := "${THISDIR}/files-uno-q:"

SRC_URI:append:uno-q = " \
    file://0001-dt-bindings-mmc-document-nvmem-layout.patch \
    file://0002-dt-bindings-net-wireless-qcom-ath10k-add-nvmem.patch \
    file://0003-dt-bindings-bluetooth-qcom-add-nvmem-bd-address.patch \
    file://0004-block-implement-nvmem-provider.patch \
    file://0005-net-of_net-add-of_get_nvmem_eui48.patch \
    file://0006-bluetooth-hci_sync-add-nvmem-backed-bd-address.patch \
    file://0007-bluetooth-qca-set-nvmem-bd-address-quirks.patch \
    file://0008-arm64-dts-qcom-arduino-imola-describe-nvmem.patch \
    file://arduino.cfg \
"
