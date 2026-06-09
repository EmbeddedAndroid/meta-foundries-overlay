# Make weston wait for the (modular, deferred-probe) DRM device before it
# starts, so it does not come up headless on qcom platforms like ventuno-q.
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"

SRC_URI += "file://10-wait-for-drm.conf"

do_install:append() {
    install -d ${D}${systemd_system_unitdir}/weston.service.d
    install -m 0644 ${UNPACKDIR}/10-wait-for-drm.conf \
        ${D}${systemd_system_unitdir}/weston.service.d/10-wait-for-drm.conf
}

FILES:${PN} += "${systemd_system_unitdir}/weston.service.d/10-wait-for-drm.conf"
