all: set-version

.PHONY: set-version
set-version:
	cp flash-uboot.py flash-uboot
	sed -i 's/@@VERSION@@/$(shell git describe --dirty --tags --always)/g' flash-uboot
	
.PHONY: clean
clean:
	rm -f flash-uboot