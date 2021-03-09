$(eval NAME := $(shell python3 setup.py --name))
$(eval PY_NAME := $(shell python3 setup.py --name | sed 's/-/_/g'))
$(eval VERSION := $(shell python3 setup.py --version))

SDIST := dist/$(NAME)-$(VERSION).tar.gz
WHEEL := dist/$(PY_NAME)-$(VERSION)-py2.py3-none-any.whl

.PHONY: all
all: build

$(SDIST):
	python3 setup.py sdist

$(WHEEL):
	python3 setup.py bdist_wheel

.PHONY: build
build: $(SDIST) $(WHEEL)

.PHONY: install
install: $(WHEEL)
	pip install --user $(WHEEL)

.PHONY: systeminstall
systeminstall: $(WHEEL)
	pip install $(WHEEL)

.PHONY: uninstall
uninstall:
	pip uninstall $(NAME)

.PHONY: upload
upload: $(SDIST) $(WHEEL)
	twine upload $(SDIST) $(WHEEL)

.PHONY: clean
clean:
	rm -rf build dist *.egg-info
