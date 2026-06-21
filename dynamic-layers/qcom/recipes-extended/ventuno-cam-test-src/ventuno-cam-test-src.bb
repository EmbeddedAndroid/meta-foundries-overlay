SUMMARY = "Source scaffold for the rubikpi3-cam-test:npu base image"
DESCRIPTION = "Ships /root/cam-test/, the source tree the dragonwing \
marketplace uses to build the rubikpi3-cam-test:npu Docker image at \
first boot. Bundles the ubuntu:24.04-based Dockerfile, the YOLOv8 + \
Haar face detection pipeline (detect.py), the dragonwing logo + \
sunglasses overlay assets, the yolov8_det.tflite model exported for \
QCS8300 HTP (V75) (w8a8) and the COCO label list, plus the aarch64 QNN host \
libraries extracted from QAIRT 2.36 (libQnnTFLiteDelegate, libQnnHtp*, \
libQnnSystem). The image itself is not baked into the rootfs: the \
dragonwing-firstboot one-shot runs 'docker build' against this tree on \
first boot so the marketplace + cam-detect tile come up working without \
shipping a 1.8GB Docker image inside the rootfs."

LICENSE = "CLOSED"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

QAIRT_VERSION = "2.43.0.260128"

SRC_URI = " \
    file://Dockerfile \
    file://detect.py \
    file://run.sh \
    file://make_logo.py \
    file://assets/sunglasses.png \
    file://assets/dragonwing-raw.png \
    file://models/yolov8_det.tflite \
    file://models/coco_labels.txt \
    https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/${QAIRT_VERSION}/v${QAIRT_VERSION}.zip;name=qairt;subdir=qairt \
"

# Same archive as rubikpi3-npu-runtime; bitbake dedupes by sha256.
SRC_URI[qairt.sha256sum] = "e3fce35419310bf80aa2947442a4b39366d80237c4bd72946b77832f71b75223"

S = "${UNPACKDIR}"

# Cannot use allarch because we ship aarch64 QAIRT host libs under qnn-libs/.
# Bind PACKAGE_ARCH to the machine instead so QA accepts arch-specific ELFs.
PACKAGE_ARCH = "${MACHINE_ARCH}"

do_install() {
    install -d ${D}/root/cam-test/assets
    install -d ${D}/root/cam-test/models
    install -d ${D}/root/cam-test/qnn-libs

    install -m 0644 ${UNPACKDIR}/Dockerfile     ${D}/root/cam-test/Dockerfile
    install -m 0755 ${UNPACKDIR}/detect.py      ${D}/root/cam-test/detect.py
    install -m 0755 ${UNPACKDIR}/run.sh         ${D}/root/cam-test/run.sh
    install -m 0644 ${UNPACKDIR}/make_logo.py   ${D}/root/cam-test/make_logo.py

    install -m 0644 ${UNPACKDIR}/assets/sunglasses.png      ${D}/root/cam-test/assets/sunglasses.png
    install -m 0644 ${UNPACKDIR}/assets/dragonwing-raw.png  ${D}/root/cam-test/assets/dragonwing-raw.png

    install -m 0644 ${UNPACKDIR}/models/yolov8_det.tflite   ${D}/root/cam-test/models/yolov8_det.tflite
    install -m 0644 ${UNPACKDIR}/models/coco_labels.txt     ${D}/root/cam-test/models/coco_labels.txt

    # Locate QNN aarch64 host libs inside the QAIRT zip. Layout has varied
    # across QAIRT versions (aarch64-oe-linux-gcc11.2, aarch64-ubuntu-gcc9.4,
    # aarch64-android, etc.); pick the first aarch64-* directory that
    # contains libQnnTFLiteDelegate.so and ship that whole lib dir.
    qnn_root="${UNPACKDIR}/qairt/qairt/${QAIRT_VERSION}/lib"
    picked=""
    for d in "$qnn_root"/aarch64-oe-linux-gcc11.2 "$qnn_root"/aarch64-oe-linux* "$qnn_root"/aarch64-ubuntu* "$qnn_root"/aarch64-android; do
        if [ -f "$d/libQnnTFLiteDelegate.so" ]; then
            picked="$d"
            break
        fi
    done
    if [ -z "$picked" ]; then
        bbfatal "rubikpi3-cam-test-src: could not find aarch64 QNN host libs in $qnn_root; contents: $(ls $qnn_root 2>/dev/null)"
    fi
    install -m 0755 $picked/libQnnCpu.so                  ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnGpu.so                  ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnGpuProfilingReader.so   ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtp.so                  ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtpPrepare.so           ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtpV75CalculatorStub.so ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnHtpV75Stub.so           ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnSystem.so               ${D}/root/cam-test/qnn-libs/
    install -m 0755 $picked/libQnnTFLiteDelegate.so       ${D}/root/cam-test/qnn-libs/
}

FILES:${PN} = "/root/cam-test"

# .so files inside /root/cam-test/qnn-libs/ are aarch64 host ELFs (same arch as
# target) but get copied as data, not linked. Skip standard library QA — they
# are not part of the system runtime path.
INSANE_SKIP:${PN} += "already-stripped ldflags dev-so libdir"

COMPATIBLE_MACHINE = "(ventuno-q)"
