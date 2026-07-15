SUMMARY = "Source scaffold for the rubikpi3-cam-test:npu base image (IQ-9075 EVK / Hexagon V73)"
DESCRIPTION = "Ships /root/cam-test/, the source tree the dragonwing \
marketplace uses to build the rubikpi3-cam-test:npu Docker image at \
first boot. IQ-9075 EVK (QCS9075 / sa8775p) variant: identical app code, \
models and assets to the VENTUNO Q recipe -- only the QAIRT Hexagon host \
stubs differ (V73 here vs V75 on qcs8300, V68 on qcm6490). The image itself \
is not baked into the rootfs: dragonwing-firstboot runs 'docker build' \
against this tree so the marketplace + cam-detect tile come up working \
without shipping a 1.8GB Docker image inside the rootfs."

LICENSE = "CLOSED"

# Share the VENTUNO recipe's files verbatim -- the Dockerfile, detect.py,
# run.sh, make_logo.py, assets and the (device-agnostic) tflite models are
# byte-identical across boards; only the Hexagon stub version below differs.
# Pointing at one copy instead of forking a third is deliberate: the earlier
# per-board duplication is exactly what let rubikpi3 drift to QAIRT 2.36 while
# ventuno was on 2.43, which broke NPU inference with a version-mismatched skel.
FILESEXTRAPATHS:prepend := "${THISDIR}/../ventuno-cam-test-src/files:"

# Must match the qairt-sdk / qairt-sdk-hexagon-v73 version the machine pulls,
# or the HLOS stubs here won't match the on-device DSP skel and the HTP
# delegate fails to load (see the 2.36-vs-2.43 regression).
QAIRT_VERSION = "2.43.0.260128"

SRC_URI = " \
    file://Dockerfile \
    file://detect.py \
    file://run.sh \
    file://make_logo.py \
    file://assets/sunglasses.png \
    file://assets/dragonwing-raw.png \
    file://models/yolov8_det.tflite \
    file://models/face_det_lite.tflite \
    file://models/coco_labels.txt \
    https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/${QAIRT_VERSION}/v${QAIRT_VERSION}.zip;name=qairt;subdir=qairt \
"

SRC_URI[qairt.sha256sum] = "e3fce35419310bf80aa2947442a4b39366d80237c4bd72946b77832f71b75223"

S = "${UNPACKDIR}"

# Cannot use allarch because we ship aarch64 QAIRT host libs under qnn-libs/.
# Bind PACKAGE_ARCH to the machine instead so QA accepts arch-specific ELFs.
PACKAGE_ARCH = "${MACHINE_ARCH}"

do_install() {
    install -d ${D}${datadir}/dragonwing/cam-test
    install -d ${D}${datadir}/dragonwing/cam-test/assets
    install -d ${D}${datadir}/dragonwing/cam-test/models
    install -d ${D}${datadir}/dragonwing/cam-test/qnn-libs

    install -m 0644 ${UNPACKDIR}/Dockerfile     ${D}${datadir}/dragonwing/cam-test/Dockerfile
    install -m 0755 ${UNPACKDIR}/detect.py      ${D}${datadir}/dragonwing/cam-test/detect.py
    install -m 0755 ${UNPACKDIR}/run.sh         ${D}${datadir}/dragonwing/cam-test/run.sh
    install -m 0644 ${UNPACKDIR}/make_logo.py   ${D}${datadir}/dragonwing/cam-test/make_logo.py

    install -m 0644 ${UNPACKDIR}/assets/sunglasses.png      ${D}${datadir}/dragonwing/cam-test/assets/sunglasses.png
    install -m 0644 ${UNPACKDIR}/assets/dragonwing-raw.png  ${D}${datadir}/dragonwing/cam-test/assets/dragonwing-raw.png

    install -m 0644 ${UNPACKDIR}/models/yolov8_det.tflite    ${D}${datadir}/dragonwing/cam-test/models/yolov8_det.tflite
    install -m 0644 ${UNPACKDIR}/models/face_det_lite.tflite ${D}${datadir}/dragonwing/cam-test/models/face_det_lite.tflite
    install -m 0644 ${UNPACKDIR}/models/coco_labels.txt      ${D}${datadir}/dragonwing/cam-test/models/coco_labels.txt

    # Locate QNN aarch64 host libs inside the QAIRT zip. Layout has varied
    # across QAIRT versions (aarch64-oe-linux-gcc11.2, aarch64-ubuntu-gcc9.4,
    # ...), so probe rather than hard-code.
    qnn_root="${UNPACKDIR}/qairt/qairt/${QAIRT_VERSION}/lib"
    picked=""
    for d in $qnn_root/aarch64-oe-linux-* $qnn_root/aarch64-ubuntu-* $qnn_root/aarch64-*; do
        if [ -f "$d/libQnnHtp.so" ]; then
            picked="$d"
            break
        fi
    done
    if [ -z "$picked" ]; then
        bbfatal "iq9075-cam-test-src: no aarch64 QNN host lib dir with libQnnHtp.so under $qnn_root"
    fi

    install -m 0755 $picked/libQnnCpu.so                  ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnGpu.so                  ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnGpuProfilingReader.so   ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtp.so                  ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtpPrepare.so           ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    # V73: QCS9075 / sa8775p Hexagon. The stub must match the SoC's DSP skel
    # (qairt-sdk-hexagon-v73, pulled by the iq-9075-evk machine config).
    install -m 0755 $picked/libQnnHtpV73CalculatorStub.so ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtpV73Stub.so           ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnSystem.so               ${D}${datadir}/dragonwing/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnTFLiteDelegate.so       ${D}${datadir}/dragonwing/cam-test/qnn-libs/
}

FILES:${PN} = "${datadir}/dragonwing/cam-test"

# .so files inside /root/cam-test/qnn-libs/ are aarch64 host ELFs (same arch as
# target) but get copied as data, not linked. Skip standard library QA — they
# are not part of the system runtime path.
INSANE_SKIP:${PN} += "already-stripped ldflags dev-so libdir"

COMPATIBLE_MACHINE = "(iq-9075-evk)"
