FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-base gstreamer1.0-libav v4l-utils \
        python3 python3-pip python3-numpy python3-opencv python3-gi opencv-data \
        ca-certificates libyaml-0-2 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --break-system-packages ai-edge-litert

COPY qnn-libs/ /opt/qnn/
COPY models/ /models/
COPY detect.py /detect.py
COPY run.sh /run.sh
COPY make_logo.py /make_logo.py
COPY assets/ /raw-assets/
RUN chmod +x /detect.py /run.sh && mkdir -p /assets && python3 /make_logo.py

ENV LD_LIBRARY_PATH=/opt/qnn:/usr/lib
ENTRYPOINT ["/run.sh"]
