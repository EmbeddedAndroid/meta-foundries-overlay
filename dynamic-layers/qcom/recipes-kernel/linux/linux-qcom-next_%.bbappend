# In-flight kernel changes for UNO Q (Arduino UNO Q / QRB2210 / imola).
#
# Five pieces:
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
#  4. arduino-imola DTS holding fix (0009-): disables anx7625 +
#     forces usb_dwc3 dr_mode=peripheral. The anx7625 driver
#     NULL-derefs in drm_atomic_state_alloc at probe on this kernel,
#     which tears down the DRM stack mid-init and prevents userspace
#     from reaching multi-user.target (rmtfs/tqftpserv never start ->
#     no wifi). See feedback memory uart-console-loop-diagnosis and
#     anx7625-panic-and-dts-disable. Drop when upstream fix lands.
#
#  5. qcom_scm qseecom allowlist add (0010-): "arduino,imola". The
#     qcom_scm driver guards qseecom binding behind a hard-coded list
#     of validated machines; without an entry the kernel logs
#     "qseecom: untested machine, skipping" and the qseecom platform
#     device is never registered. Consequence on UNO Q is that the
#     TZ-side TAs (uefisecapp, etc.) are unreachable from Linux, UEFI
#     runtime variable services return EFI_DEVICE_ERROR, and
#     systemd-gpt-auto-generator can't pick up the ESP. Adding the
#     "arduino,imola" compatible to the allowlist is a small,
#     reversible enabler. The qseecom re-entrancy concern noted in
#     the comment immediately above the allowlist still applies;
#     watch for SCM call deadlocks if the QRB2210 platform triggers
#     re-entrant TA invocations.
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
    file://0009-uno-q-dts-disable-anx7625-to-break-probe-cycle.patch \
    file://0010-firmware-qcom-scm-allow-qseecom-on-arduino-imola.patch \
    file://arduino.cfg \
"

# In-flight Rubik Pi 3 patches not yet in qcom-next:
#   e8bd92c4a0d2 drm/bridge: lt9611: Add support for single Port B input
#   ebcf2240a249 arm64: dts: qcom: qcs6490-rubikpi3: Use lt9611 DSI Port B
#   draft        arm64: dts: qcom: qcs6490-rubikpi3: enable AP6256 SDIO WiFi
#   v4 1-4/4     misc: fastrpc: Add missing bug fixes (Jianping Li, lore)
#   draft        misc: fastrpc: refcount fastrpc_user from each buf (UAF fix)
# Plus kconfig fragments to enable BCM4345C5 UART HCI (Bluetooth) and
# brcmfmac SDIO (WiFi). Pulled from the rubrikpi3-next branch maintained
# in EmbeddedAndroid/meta-qcom-3rdparty alongside the marketplace work.
# 0006-fastrpc-alloc-entire-audiopd-rmem-in-probe.patch is kept on disk
# but intentionally NOT in SRC_URI: it overlaps the lighter audiopd-init
# alloc fix in 0004, and the 0004 + 0007 path is what matches mainline.
# Kept for diagnostic re-bisects if the audiopd path needs rework.
FILESEXTRAPATHS:prepend:qcs6490-thundercomm-rubikpi3 := "${THISDIR}/qcs6490-thundercomm-rubikpi3:"

SRC_URI:append:qcs6490-thundercomm-rubikpi3 = " \
    file://0001-lt9611-port-b.patch \
    file://0002-dts-port-b.patch \
    file://0003-wifi-sdio.patch \
    file://0004-fastrpc-fix-audiopd-initial-alloc.patch \
    file://0005-fastrpc-remove-buf-from-list-before-unmap.patch \
    file://0007-fastrpc-buf-free-accept-null.patch \
    file://0008-fastrpc-refcount-fl-from-dmabuf.patch \
    file://bt-bcm.cfg \
    file://wifi-bcm.cfg \
"

# fastrpc backports were authored against mainline; they apply with
# offset/fuzz at our qcom-next SRCREV. Demote patch-fuzz from error
# to warning so the build proceeds. Refresh the patches against the
# pinned SRCREV when the SRCREV bumps.
ERROR_QA:remove:qcs6490-thundercomm-rubikpi3 = "patch-fuzz"
WARN_QA:append:qcs6490-thundercomm-rubikpi3 = " patch-fuzz"

# misc: fastrpc — fix context leak + hang on signal-interrupted invoke
# (Anandu Krishnan E, lore drm-ai-reviews 2026-05-25). Touches only
# drivers/misc/fastrpc.c. The patch is kernel-version-specific: it applies
# to the 7.1-rc4+git tree (verified on ventuno-q) but NOT to the 7.0+git
# tree used by rb3gen2/rubikpi3, where fastrpc.c differs (do_patch fails).
# Scope it to ventuno-q only; rb3gen2/rubikpi3 (7.0) and uno-q (7.1 but a
# different SRCREV) would each need the patch rebased + verified for their
# tree. Demote patch-fuzz from error to warning where it does apply.
# https://lore.gitlab.freedesktop.org/drm-ai-reviews/20260525124222.3082420-1-anandu.e@oss.qualcomm.com/
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append:ventuno-q = " file://0001-misc-fastrpc-fix-context-leak-and-hang.patch"
ERROR_QA:remove:ventuno-q = "patch-fuzz"
WARN_QA:append:ventuno-q = " patch-fuzz"
