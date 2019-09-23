all: set-version

.PHONY: set-version
set-version:
	sed -i 's/@@VERSION@@/$(shell git describe --long --tags --dirty)/g' flash-uboot.py