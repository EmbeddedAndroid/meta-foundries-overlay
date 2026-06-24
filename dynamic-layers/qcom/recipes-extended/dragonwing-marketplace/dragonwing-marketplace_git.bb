SUMMARY = "Dragonwing Agentic Developer Experience marketplace"
DESCRIPTION = "Single-file Python http.server that serves a chat-first agent \
plus an app marketplace on :8080. Manages /root/apps/<id>/ scaffolds, \
spawns docker containers for each app with the right mounts/devices for \
camera + NPU + Wayland, and persists state under /var/lib/dragonwing-*. \
Source is vendored under files/ (snapshot of EmbeddedAndroid/age@8a08988) \
to avoid a git fetch against a private remote at bitbake time."

LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI = " \
    file://marketplace.py \
    file://html.py \
    file://static/ \
    file://dragonwing-marketplace.service \
    file://dragonwing-rootseed.conf \
    file://dragonwing-state.conf \
"

inherit allarch systemd

SYSTEMD_SERVICE:${PN} = "dragonwing-marketplace.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d ${D}${datadir}/dragonwing/marketplace
    install -m 0755 ${UNPACKDIR}/marketplace.py ${D}${datadir}/dragonwing/marketplace/marketplace.py
    install -m 0644 ${UNPACKDIR}/html.py        ${D}${datadir}/dragonwing/marketplace/html.py

    install -d ${D}${datadir}/dragonwing/marketplace/static
    install -m 0644 ${UNPACKDIR}/static/*       ${D}${datadir}/dragonwing/marketplace/static/

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/dragonwing-marketplace.service \
        ${D}${systemd_system_unitdir}/dragonwing-marketplace.service

    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${UNPACKDIR}/dragonwing-rootseed.conf \
        ${D}${nonarch_libdir}/tmpfiles.d/dragonwing-rootseed.conf

    # Runtime state dirs. Created + owned via tmpfiles at boot (NOT baked into
    # /var, which is stateful on ostree): /feeds must be writable by uid 1000
    # because app containers run as --user 1000:1000 and write their live
    # preview JPEG there, while the marketplace (root) only reads it.
    install -m 0644 ${UNPACKDIR}/dragonwing-state.conf \
        ${D}${nonarch_libdir}/tmpfiles.d/dragonwing-state.conf
}

FILES:${PN} = " \
    ${datadir}/dragonwing/marketplace \
    ${systemd_system_unitdir}/dragonwing-marketplace.service \
    ${nonarch_libdir}/tmpfiles.d/dragonwing-rootseed.conf \
    ${nonarch_libdir}/tmpfiles.d/dragonwing-state.conf \
"

RDEPENDS:${PN} = " \
    python3-core \
    python3-modules \
    docker-moby \
"

# marketplace.py is a Python script; nothing to strip and no host-paths to
# audit. Suppress the noisy QA classes that don't apply.
INSANE_SKIP:${PN} += "already-stripped"

# Lock the installed files at first boot so the on-device agent (which runs
# as root via the marketplace's bash tool) cannot rewrite the runtime in
# place. Live changes to /root/marketplace/* are not the supported path —
# the agent should propose patches to /tmp instead and the operator bumps
# the vendored snapshot in this recipe. Pairs with the SYSTEM_PROMPT rule.
