# cam-detect source — forkable scaffold around the baked rubikpi3-cam-test:npu
# image. Fork this app and edit main.py to customize the detection pipeline;
# everything else (NPU runtime, libs, Wayland sink, camera handling) is
# pre-staged inside the base image so builds are fast (just one COPY layer).
FROM rubikpi3-cam-test:npu

COPY main.py /detect.py
COPY run.sh  /run.sh
COPY assets/ /assets/

ENTRYPOINT ["/run.sh"]
