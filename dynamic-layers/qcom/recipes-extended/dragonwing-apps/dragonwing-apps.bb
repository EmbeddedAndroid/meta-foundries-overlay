SUMMARY = "Dragonwing marketplace app scaffolds (/root/apps)"
DESCRIPTION = "Source scaffolds the Dragonwing marketplace expects to find \
under /root/apps/<id>/ — the canonical _template starting point and the \
cam-detect (Deal With It) app whose Fork/Modify/Export flows in the \
marketplace UI clone, snapshot and rebuild against. _template's Dockerfile \
documents the ubuntu:24.04 + GLIBC 2.39 + ai-edge-litert + libyaml-0-2 \
combo that's been validated end-to-end on this board; cam-detect inherits \
FROM rubikpi3-cam-test:npu (built by rubikpi3-cam-test-src) for fast \
single-COPY-layer fork rebuilds."

LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI = " \
    file://_template/Dockerfile \
    file://_template/main.py \
    file://_template/run.sh \
    file://_template/README.md \
    file://_template/assets/dragonwing.png \
    file://cam-detect/Dockerfile \
    file://cam-detect/main.py \
    file://cam-detect/run.sh \
    file://cam-detect/README.md \
    file://cam-detect/assets/dragonwing.png \
"

S = "${UNPACKDIR}"

inherit allarch

do_install() {
    install -d ${D}/root/apps/_template/assets
    install -m 0644 ${UNPACKDIR}/_template/Dockerfile ${D}/root/apps/_template/Dockerfile
    install -m 0755 ${UNPACKDIR}/_template/main.py    ${D}/root/apps/_template/main.py
    install -m 0755 ${UNPACKDIR}/_template/run.sh     ${D}/root/apps/_template/run.sh
    install -m 0644 ${UNPACKDIR}/_template/README.md  ${D}/root/apps/_template/README.md
    install -m 0644 ${UNPACKDIR}/_template/assets/dragonwing.png \
        ${D}/root/apps/_template/assets/dragonwing.png

    install -d ${D}/root/apps/cam-detect/assets
    install -m 0644 ${UNPACKDIR}/cam-detect/Dockerfile ${D}/root/apps/cam-detect/Dockerfile
    install -m 0755 ${UNPACKDIR}/cam-detect/main.py    ${D}/root/apps/cam-detect/main.py
    install -m 0755 ${UNPACKDIR}/cam-detect/run.sh     ${D}/root/apps/cam-detect/run.sh
    install -m 0644 ${UNPACKDIR}/cam-detect/README.md  ${D}/root/apps/cam-detect/README.md
    install -m 0644 ${UNPACKDIR}/cam-detect/assets/dragonwing.png \
        ${D}/root/apps/cam-detect/assets/dragonwing.png
}

FILES:${PN} = "/root/apps"
