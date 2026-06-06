# TEMP HACK (ventuno-q only): the Arduino VENTUNO Q's QCA2066 Wi-Fi
# module reports an unprovisioned board id (qmi-board-id 0xff), so the
# upstream ath11k/QCA2066/hw2.1/board-2.bin has no matching BDF and
# ath11k falls back to a generic one -> WMI/scan timeouts (radio never
# scans). Until the proper VENTUNO QCA2066 calibration (bdwlan) is
# available from Arduino/Qualcomm, alias the 0108/chip-18/board-778
# calibration (the closest match for this 17cb:0108 module) onto this
# module's lookup by shipping a minimal board-2.bin.
#
# Scoped to ventuno-q via PACKAGE_ARCH so the shared (allarch)
# linux-firmware for other machines is untouched.
#
# REMOVE once a correct, calibrated VENTUNO board-2.bin exists.

FILESEXTRAPATHS:prepend:ventuno-q := "${THISDIR}/${PN}:"
SRC_URI:append:ventuno-q = " file://board-2-qca2066-ventuno.bin"
PACKAGE_ARCH:ventuno-q = "${MACHINE_ARCH}"

do_install:append:ventuno-q() {
    install -d ${D}${firmwaredir}/ath11k/QCA2066/hw2.1
    install -m 0644 ${UNPACKDIR}/board-2-qca2066-ventuno.bin \
        ${D}${firmwaredir}/ath11k/QCA2066/hw2.1/board-2.bin
}
