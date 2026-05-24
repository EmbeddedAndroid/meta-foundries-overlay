SUMMARY = "Factory image extending qcom-multimedia-image with Foundries tooling"
LICENSE = "MIT"

require recipes-products/images/qcom-multimedia-image.bb
require recipes-samples/images/feature-fio.inc

IMAGE_FEATURES += "ssh-server-openssh"

# docker-cli-config provides /usr/lib/docker/config.json pointing
# at hub.foundries.io. Not in packagegroup-foundries (overlay-specific
# default, not product-mandatory).
CORE_IMAGE_BASE_INSTALL += "docker-cli-config"
