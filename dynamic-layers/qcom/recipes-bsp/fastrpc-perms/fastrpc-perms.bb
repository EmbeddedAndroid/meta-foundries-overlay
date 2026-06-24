SUMMARY = "udev rule granting the video group access to Hexagon fastrpc nodes"
DESCRIPTION = "Ships /lib/udev/rules.d/71-fastrpc-perms.rules so containerised \
NPU apps (run as uid 1000 + group video) can open /dev/fastrpc-{cdsp,adsp} \
to reach the QNN HTP / cDSP backend. The kernel creates these nodes root:root \
0600 by default, which blocks the non-root app containers."
LICENSE = "CLOSED"

SRC_URI = "file://71-fastrpc-perms.rules"

inherit allarch

do_install() {
    install -d ${D}${nonarch_base_libdir}/udev/rules.d
    install -m 0644 ${UNPACKDIR}/71-fastrpc-perms.rules \
        ${D}${nonarch_base_libdir}/udev/rules.d/71-fastrpc-perms.rules
}

FILES:${PN} = "${nonarch_base_libdir}/udev/rules.d/71-fastrpc-perms.rules"
