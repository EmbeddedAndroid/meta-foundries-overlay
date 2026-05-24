SUMMARY = "Foundries factory image (Intel x86_64)"
LICENSE = "MIT"

require recipes-core/images/core-image-base.bb
require recipes-samples/images/feature-fio.inc

IMAGE_FEATURES += "ssh-server-openssh"

# docker-cli-config seeds /usr/lib/docker/config.json pointing at
# hub.foundries.io. Overlay-specific default, not in
# packagegroup-foundries.
CORE_IMAGE_BASE_INSTALL += "docker-cli-config"

# Flashable wic image. core-image-base will produce wic.gz + bmap
# pair when IMAGE_FSTYPES asks for them; the machine config in
# meta-intel selects the default WKS_FILE.
IMAGE_FSTYPES += "wic wic.bmap wic.gz"
