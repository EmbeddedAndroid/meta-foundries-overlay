# In-flight kernel changes for UNO Q (Arduino UNO Q / QRB2210 / imola).
#
# Three pieces:
#
#  1. SRCREV bump for uno-q only. meta-qcom pins linux-qcom-next at
#     qcom-next-7.0-20260507 (6e159a33b). For UNO Q we want the latest
#     qcom-next tag so we pick up imola-relevant BSP work without
#     waiting for meta-qcom to bump. Pinned (not AUTOREV) so builds
#     are reproducible. Bump this when a newer qcom-next-* tag ships.
#
#  2. block-as-nvmem v2 patch series (Loic Poulain, oss.qualcomm.com,
#     2026-05-07). Adds NVMEM-provider semantics to MMC + ath10k + qca
#     Bluetooth, and the arduino-imola DTS that consumes them. Required
#     for stable WLAN/BT MAC addresses on UNO Q. Submitted upstream.
#     https://lore.kernel.org/all/20260507-block-as-nvmem-v2-0-bf17edd5134e@oss.qualcomm.com/
#     Verified 2026-05-26: none of the 8 patches are present in
#     qcom-next HEAD df3ae9703 (qcom-next-7.1-rc4-20260524).
#
#  3. arduino.cfg kconfig fragment. Pulled verbatim from
#     github.com/arduino/arduino-deb-images@kernel-configs/arduino.config.
#     UNO Q userspace stack (audio, BT, exFAT, ANX bridge, ZRAM/ZSWAP)
#     expects these knobs set.
#
# Drop the patch set + arduino.cfg once block-as-nvmem v2 lands in
# qcom-next and the arduino knobs graduate into meta-qcom's
# bsp-additions.cfg. Drop the SRCREV override once meta-qcom pins a
# tag at least as new as the one named below.

# qcom-next-7.1-rc4-20260524 -- 17 days newer than meta-qcom's pin,
# kernel base bumps from 7.0 to 7.1-rc4.
SRCREV:uno-q = "df3ae9703774b70a7b7758b53498a25de9f87174"
LINUX_VERSION:uno-q = "7.1"

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
