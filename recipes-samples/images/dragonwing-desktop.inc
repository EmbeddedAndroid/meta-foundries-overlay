# Dragonwing Weston desktop UI experience for HDMI-equipped qcom boards:
# wallpaper, Marketplace panel launcher (Qdemo removed), kiosk helpers, and the
# kiosk container build context. require'd by the qcom factory images that have
# weston + HDMI.
#
# The branding weston.ini is shipped read-only under /usr/share/dragonwing and
# applied over the stock /etc/xdg/weston/weston.ini here (after all packages are
# laid down) so it never collides with the weston-init-owned file at do_rootfs,
# and still wins. /etc is writable+persistent on ostree, so the baked override
# survives reboots and OTA.

IMAGE_INSTALL:append = " dragonwing-weston-desktop"

foundries_dragonwing_weston_ini () {
    if [ -f ${IMAGE_ROOTFS}${datadir}/dragonwing/weston.ini ]; then
        install -d ${IMAGE_ROOTFS}${sysconfdir}/xdg/weston
        install -m 0644 ${IMAGE_ROOTFS}${datadir}/dragonwing/weston.ini \
            ${IMAGE_ROOTFS}${sysconfdir}/xdg/weston/weston.ini
        bbnote "dragonwing-desktop: applied branding weston.ini to ${sysconfdir}/xdg/weston/weston.ini"
    fi
}
ROOTFS_POSTPROCESS_COMMAND += "foundries_dragonwing_weston_ini;"
