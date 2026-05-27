# Dragonwing App Template - proven base for QCS6490 camera/NPU apps.
#
# - ubuntu:24.04 = GLIBC 2.39 (host libcdsprpc.so requires >=2.38)
# - python3.12 + python3-opencv + opencv-data (Haar cascades)
# - ai-edge-litert: modern TFLite runtime, wheels for py3.12+
# - libyaml-0-2: needed transitively by libQnnHtp.so HtpProvider
# - GStreamer plugins-{base,good,bad}: covers v4l2src + jpegdec +
#   videoconvert + waylandsink + appsink/appsrc + Haar cascades
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base gstreamer1.0-libav v4l-utils \
        python3 python3-pip python3-numpy python3-opencv python3-gi \
        opencv-data libyaml-0-2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir ai-edge-litert

# QNN host-side libs (caller bind-mounts /opt/qnn at runtime OR bakes them in)
ENV LD_LIBRARY_PATH=/opt/qnn:/usr/lib

# App files - REPLACE WITH YOUR APP
COPY main.py /main.py
COPY run.sh  /run.sh
COPY assets/ /assets/
RUN chmod +x /main.py /run.sh

ENTRYPOINT ["/run.sh"]
