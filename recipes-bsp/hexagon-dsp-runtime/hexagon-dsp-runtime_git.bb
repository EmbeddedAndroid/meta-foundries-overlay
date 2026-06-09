SUMMARY = "Hexagon cDSP/aDSP/gDSP FastRPC runtime for QCS8300 (Arduino Monza)"
DESCRIPTION = "DSP-side FastRPC runtime (fastrpc_shell_* and signed system skels) \
from linux-msm/hexagon-dsp-binaries, required for cDSP/aDSP FastRPC (NPU offload). \
The shell build MUST match the on-device DSP firmware (cdsp0.mbn) build; this recipe \
pins DSP.AT.1.0.1-00196-LEMANS-2 to match the qcs8300 firmware shipped in the image. \
hexagon-dsp-binaries maps qcs8300/Arduino/Monza -> QCS8300-RIDE."
HOMEPAGE = "https://github.com/linux-msm/hexagon-dsp-binaries"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE.MIT;md5=3e312ffe200717dca92f8cec0dae6290"

SRC_URI = "git://github.com/linux-msm/hexagon-dsp-binaries.git;branch=trunk;protocol=https"
SRCREV = "68efa4770d51fb2ba881d28f9c46af9c02fc878f"

COMPATIBLE_MACHINE = "ventuno-q"

# Prebuilt Hexagon (DSP) ELF binaries - not host/ARM objects.
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INHIBIT_SYSROOT_STRIP = "1"
INSANE_SKIP:${PN} += "arch ldflags textrel already-stripped staticdev libdir"

RIDE = "qcs8300/Qualcomm/QCS8300-RIDE"
CDSP_VER = "cdsp-DSP.AT.1.0.1-00196-LEMANS-2"
ADSP_VER = "adsp-DSP.AT.1.0.1-00196-LEMANS-2"
GDSP_VER = "gdsp0-DSP.AT.1.0.1-00196-LEMANS-2"

do_install() {
    install -d ${D}${libdir}/dsp/cdsp ${D}${libdir}/dsp/adsp ${D}${libdir}/dsp/gdsp0
    cp -rL ${S}/${RIDE}/${CDSP_VER}/. ${D}${libdir}/dsp/cdsp/
    cp -rL ${S}/${RIDE}/${ADSP_VER}/. ${D}${libdir}/dsp/adsp/
    cp -rL ${S}/${RIDE}/${GDSP_VER}/. ${D}${libdir}/dsp/gdsp0/
}

FILES:${PN} = "${libdir}/dsp"
