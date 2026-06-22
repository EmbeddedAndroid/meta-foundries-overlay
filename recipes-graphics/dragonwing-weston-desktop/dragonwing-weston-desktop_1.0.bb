SUMMARY = "Dragonwing Weston desktop: wallpaper, panel branding, marketplace kiosk"
DESCRIPTION = "Installs the Dragonwing desktop wallpaper, the Marketplace panel \
icon + dragonwing-kiosk-{start,stop} helpers that drive the containerised \
Chromium kiosk, and the weston.service docker-socket drop-in. The branding \
weston.ini is staged read-only under ${datadir}/dragonwing and applied over \
the stock /etc/xdg/weston/weston.ini by the image (ROOTFS_POSTPROCESS) so it \
never collides with the weston-init-owned file at do_rootfs. See DEPLOY.md for \
the kiosk container image (NOT baked here). Originally EmbeddedAndroid art bundle."
LICENSE = "CLOSED"

SRC_URI = " \
    file://weston.ini \
    file://weston-docker-group.conf \
    file://dragonwing-wallpaper.png \
    file://kiosk-marketplace.png \
    file://kiosk-start.sh \
    file://kiosk-stop.sh \
    file://kiosk/Dockerfile \
    file://kiosk/launch.sh \
"

S = "${WORKDIR}"
inherit allarch

do_install() {
    # Branding weston.ini -- STAGED only (the image's ROOTFS_POSTPROCESS copies
    # it over /etc/xdg/weston/weston.ini; shipping it to /etc directly would
    # collide with the weston-init package at do_rootfs).
    install -d ${D}${datadir}/dragonwing
    install -m 0644 ${WORKDIR}/weston.ini ${D}${datadir}/dragonwing/weston.ini

    # weston.service docker-socket access for the panel launchers (run as the
    # weston user). Unique drop-in file -- coexists with weston-init's.
    install -d ${D}${sysconfdir}/systemd/system/weston.service.d
    install -m 0644 ${WORKDIR}/weston-docker-group.conf \
        ${D}${sysconfdir}/systemd/system/weston.service.d/10-docker-group.conf

    # Wallpaper + 24x24 panel icon (weston 15 draws launcher icons at native
    # size, so they MUST be 24x24).
    install -d ${D}${datadir}/dragonwing/icons
    install -m 0644 ${WORKDIR}/dragonwing-wallpaper.png ${D}${datadir}/dragonwing/dragonwing-wallpaper.png
    install -m 0644 ${WORKDIR}/kiosk-marketplace.png    ${D}${datadir}/dragonwing/icons/kiosk-marketplace.png

    # Kiosk launcher target + stop helper.
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/kiosk-start.sh ${D}${bindir}/dragonwing-kiosk-start
    install -m 0755 ${WORKDIR}/kiosk-stop.sh  ${D}${bindir}/dragonwing-kiosk-stop

    # Kiosk container build context (Chromium + mesa 26). NOT baked as an
    # image; dragonwing-firstboot docker-builds marketplace-kiosk:latest
    # from here on first boot (best-effort). Read-only /usr is fine -- docker
    # build only reads the context.
    install -d ${D}${datadir}/dragonwing/kiosk
    install -m 0644 ${WORKDIR}/kiosk/Dockerfile ${D}${datadir}/dragonwing/kiosk/Dockerfile
    install -m 0755 ${WORKDIR}/kiosk/launch.sh  ${D}${datadir}/dragonwing/kiosk/launch.sh
}

FILES:${PN} += " \
    ${datadir}/dragonwing \
    ${sysconfdir}/systemd/system/weston.service.d/10-docker-group.conf \
    ${bindir}/dragonwing-kiosk-start \
    ${bindir}/dragonwing-kiosk-stop \
"

# weston (compositor + stock terminal launcher icon) and docker (the panel
# launcher docker-runs the kiosk). The kiosk container IMAGE is delivered
# separately (firstboot build / registry) -- see dragonwing-firstboot.
RDEPENDS:${PN} += "weston docker"
