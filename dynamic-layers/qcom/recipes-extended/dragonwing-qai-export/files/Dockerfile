FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv build-essential \
        ca-certificates curl git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
        "torch>=2.1,<2.9" "torchvision" \
        "ultralytics" gitpython \
        "qai-hub" "qai-hub-models[yolov8-det]"
ENTRYPOINT ["/bin/bash","-l","-c"]
