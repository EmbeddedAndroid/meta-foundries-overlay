SUMMARY = "Dockerfile scaffold for the qai-export AI Hub build image"
DESCRIPTION = "Ships /root/qai-export/Dockerfile — the build image \
definition the marketplace's 'compile model' workflow uses (torch + \
ultralytics + qai-hub + qai-hub-models[yolov8-det]). The image itself \
is too large (>3GB pulled deps) to bake into the rootfs; it is built \
on demand from this Dockerfile by the marketplace agent or by hand. \
Note: the AI Hub API token at /root/.qai_hub/client.ini is a per-user \
secret and is NOT shipped here — see /usr/share/doc/dragonwing/README \
for post-flash setup."

LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI = "file://Dockerfile"

S = "${UNPACKDIR}"

inherit allarch

do_install() {
    install -d ${D}${datadir}/dragonwing/qai-export
    install -m 0644 ${UNPACKDIR}/Dockerfile ${D}${datadir}/dragonwing/qai-export/Dockerfile
}

FILES:${PN} = "${datadir}/dragonwing/qai-export"
