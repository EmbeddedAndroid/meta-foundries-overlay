SUMMARY = "First-boot orchestrator: build cam-test docker image, seed /opt/qnn-libs"
DESCRIPTION = "Systemd one-shot that runs once on first boot to (a) copy \
the aarch64 QNN host libraries shipped by rubikpi3-cam-test-src into \
/opt/qnn-libs so the marketplace's generic-app bind mount \
-v /opt/qnn-libs:/opt/qnn resolves, and (b) docker build the \
rubikpi3-cam-test:npu image that cam-detect and forks FROM. Sequenced \
Before=dragonwing-marketplace.service so the first marketplace request \
to launch cam-detect sees an image that already exists locally. Guarded \
by ConditionPathExists=!/var/lib/dragonwing-firstboot.done so subsequent \
boots are no-ops."

LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI = " \
    file://dragonwing-firstboot \
    file://dragonwing-firstboot.service \
"

S = "${UNPACKDIR}"

inherit allarch systemd

SYSTEMD_SERVICE:${PN} = "dragonwing-firstboot.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${UNPACKDIR}/dragonwing-firstboot ${D}${bindir}/dragonwing-firstboot

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/dragonwing-firstboot.service \
        ${D}${systemd_system_unitdir}/dragonwing-firstboot.service
}

FILES:${PN} = " \
    ${bindir}/dragonwing-firstboot \
    ${systemd_system_unitdir}/dragonwing-firstboot.service \
"

RDEPENDS:${PN} = "rubikpi3-cam-test-src"

# The cam-test NPU base image differs by Hexagon arch: ventuno-q (QCS8300)
# uses the V75 variant; iq-9075-evk (QCS9075/sa8775p) the V73 one; rubikpi3 /
# rb3gen2 (QCS6490, V68) use the default. Each variant is COMPATIBLE_MACHINE-
# scoped, so a machine without an override here fails to parse with
# "Nothing RPROVIDES 'rubikpi3-cam-test-src'" -- add one per new board.
RDEPENDS:${PN}:ventuno-q = "ventuno-cam-test-src"
RDEPENDS:${PN}:iq-9075-evk = "iq9075-cam-test-src"
