.DEFAULT_GOAL := help
.ONESHELL:
SHELL := /bin/sh
.SHELLFLAGS := -eu -c

RUNTIME_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE ?= $(RUNTIME_DIR)/.env
-include $(ENV_FILE)

DOCKER ?= docker
# Source defaults only when no command-line, .env or environment override exists.
VERSION ?= $(shell . "$(RUNTIME_DIR)/build.conf"; printf '%s' "$$VERSION")
ONTOP_VERSION ?= $(shell . "$(RUNTIME_DIR)/build.conf"; printf '%s' "$$ONTOP_VERSION")
REPOSITORY ?= ghcr.io/provider-project/provider-ontop
IMAGE ?= $(REPOSITORY):$(VERSION)

.PHONY: help build publish _publish-tag-check _publish-build

help: ## Show available targets (the default)
	@awk 'BEGIN { FS = ":.*## " } /^[[:alnum:]_.-]+:.*## / { printf "make %-24s # %s\n", $$1, $$2 }' "$(RUNTIME_DIR)/Makefile"
	printf '\nVersion defaults: build.conf\nOverrides: VERSION ONTOP_VERSION REPOSITORY IMAGE DOCKER\n'

define build_image
cd "$(RUNTIME_DIR)"
$(DOCKER) build --tag "$(IMAGE)" --build-arg ONTOP_VERSION="$(ONTOP_VERSION)" .
endef

build: ## Build or replace the local runtime image
	$(build_image)

_publish-tag-check:
	sh "$(RUNTIME_DIR)/scripts/check-publish-tag.sh" "$(DOCKER)" "$(IMAGE)"

_publish-build: _publish-tag-check
	$(build_image)

publish: _publish-build ## Check remote tag, build, check known digests and push
	sh "$(RUNTIME_DIR)/scripts/check-publish-digest.sh" "$(DOCKER)" "$(IMAGE)"
	$(DOCKER) push "$(IMAGE)"
