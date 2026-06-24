# Compat symlink: /usr/lib/dsp -> the active-SoC Hexagon DSP runtime.
#
# Qualcomm's multi-SoC asset layout ships the DSP runtime under a per-SoC
# path (/usr/share/qcom/<soc>/<vendor>/<board>/dsp) and no longer provides
# the canonical /usr/lib/dsp that consumers expect (ADSP_LIBRARY_PATH, the
# Dragonwing marketplace bind-mounts -v /usr/lib/dsp:/usr/lib/dsp, anything
# loading the QNN HTP delegate). On the read-only ostree /usr the missing
# path cannot be created at runtime (docker bind-mount mkdir fails), so the
# symlink MUST be baked at image build time.
#
# DSP_RUNTIME_DIR is the active-SoC dsp dir (the one containing cdsp/ with
# the fastrpc_shell + libQnnHtpV<NN>Skel). Set per machine — the SoC/vendor/
# board components are not derivable from MACHINE alone. Mirror the path the
# qairt-sdk / hexagon-dsp-binaries recipes install to for that SoC.
#
# The postprocess only acts when DSP_RUNTIME_DIR is set AND /usr/lib/dsp does
# not already exist, so boards that still ship a real /usr/lib/dsp (or have no
# mapping) are untouched — no do_rootfs conflict, no dangling clobber.

# qcs8300 / Hexagon V75 (Arduino VENTUNO Q) — verified on hardware.
DSP_RUNTIME_DIR:ventuno-q = "${datadir}/qcom/qcs8300/Qualcomm/QCS8300-RIDE/dsp"
# qcm6490 / Hexagon V68 (RB3 Gen 2, RUBIK Pi 3) — from qairt-sdk SoC map;
# verify on first build of each (ls /usr/share/qcom/.../dsp/cdsp).
DSP_RUNTIME_DIR:rb3gen2-core-kit = "${datadir}/qcom/qcm6490/Thundercomm/RB3gen2/dsp"
DSP_RUNTIME_DIR:qcs6490-thundercomm-rubikpi3 = "${datadir}/qcom/qcm6490/Thundercomm/RB3gen2/dsp"

DSP_RUNTIME_DIR ?= ""

foundries_dsp_compat_symlink () {
    if [ -n "${DSP_RUNTIME_DIR}" ] && [ ! -e ${IMAGE_ROOTFS}${libdir}/dsp ]; then
        install -d ${IMAGE_ROOTFS}${libdir}
        ln -snf ${DSP_RUNTIME_DIR} ${IMAGE_ROOTFS}${libdir}/dsp
        bbnote "dsp-compat: ${libdir}/dsp -> ${DSP_RUNTIME_DIR}"
    fi
}
ROOTFS_POSTPROCESS_COMMAND += "foundries_dsp_compat_symlink;"

# udev rule so NPU app containers (uid 1000 + video group) can open the
# fastrpc cDSP node. See fastrpc-perms recipe.
IMAGE_INSTALL:append = " fastrpc-perms"
