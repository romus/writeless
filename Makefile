.DEFAULT_GOAL := help

PYTHON      := python3
VENV        := .venv
VENV_BIN    := $(VENV)/bin
APP_NAME    := Write Less
BUILD_DIR   := build
DIST_DIR    := $(BUILD_DIR)/dist
TEMP_DIR    := $(BUILD_DIR)/temp_
APP_VERSION := $(shell $(PYTHON) -c "import re; print(re.search(r'APP_VERSION\s*=\s*\"(.+?)\"', open('writeless/constants.py').read()).group(1))")

# Detect Python version mismatch between venv and system
SYSTEM_PY_VER := $(shell $(PYTHON) --version 2>/dev/null | awk '{print $$2}')
VENV_PY_VER   := $(shell [ -x "$(VENV_BIN)/python3" ] && $(VENV_BIN)/python3 --version 2>/dev/null | awk '{print $$2}' || echo "none")

.PHONY: help setup run build dmg zip clean version

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create/refresh venv and install dependencies
	@if [ "$(SYSTEM_PY_VER)" != "$(VENV_PY_VER)" ]; then \
		echo "==> Python version mismatch (venv: $(VENV_PY_VER), system: $(SYSTEM_PY_VER)). Recreating venv..."; \
		rm -rf "$(VENV)"; \
	fi
	@if [ ! -d "$(VENV)" ]; then \
		echo "==> Creating virtual environment..."; \
		$(PYTHON) -m venv "$(VENV)"; \
	fi
	@echo "==> Installing dependencies..."
	@$(VENV_BIN)/pip install -r requirements.txt

run: setup ## Run app in development mode
	$(VENV_BIN)/python3 app.py

build: setup ## Build Write Less.app
	@echo "==> Building $(APP_NAME) v$(APP_VERSION)"
	@if [ -d "$(BUILD_DIR)" ]; then \
		chflags -R nouchg,noschg "$(BUILD_DIR)" 2>/dev/null || true; \
		chmod -R u+rwX "$(BUILD_DIR)" 2>/dev/null || true; \
		xattr -rc "$(BUILD_DIR)" 2>/dev/null || true; \
	fi
	@rm -rf "$(BUILD_DIR)"
	@echo "==> Building $(APP_NAME).app with py2app..."
	@COPYFILE_DISABLE=1 $(VENV_BIN)/python3 setup.py py2app \
		--bdist-base="$(BUILD_DIR)/py2app" \
		--dist-dir="$(DIST_DIR)"
	@echo "==> Done! $(DIST_DIR)/$(APP_NAME).app is ready."

zip: build ## Build .app + create ZIP archive
	$(eval ZIP_NAME := WriteLess-$(APP_VERSION).zip)
	@echo "==> Creating $(ZIP_NAME)..."
	@cd "$(DIST_DIR)" && ditto -c -k --keepParent "$(APP_NAME).app" "$(ZIP_NAME)"
	@echo "==> SHA256: $$(shasum -a 256 "$(DIST_DIR)/$(ZIP_NAME)" | awk '{print $$1}')"
	@echo "==> Done! $(DIST_DIR)/$(ZIP_NAME) is ready."

dmg: build ## Build .app + create DMG installer
	$(eval DMG_NAME := WriteLess-$(APP_VERSION).dmg)
	@echo "==> Creating $(DMG_NAME)..."
	@mkdir -p "$(TEMP_DIR)"
	@mv "$(DIST_DIR)/$(APP_NAME).app" "$(TEMP_DIR)/"
	@hdiutil create -volname "$(APP_NAME)" -srcfolder "$(TEMP_DIR)" -ov -format UDZO "$(DIST_DIR)/$(DMG_NAME)" || \
		(mv "$(TEMP_DIR)/$(APP_NAME).app" "$(DIST_DIR)/" && exit 1)
	@mv "$(TEMP_DIR)/$(APP_NAME).app" "$(DIST_DIR)/"
	@rm -rf "$(TEMP_DIR)"
	@echo "==> Done! $(DIST_DIR)/$(DMG_NAME) is ready."

clean: ## Remove build artifacts
	@if [ -d "$(BUILD_DIR)" ]; then \
		chflags -R nouchg,noschg "$(BUILD_DIR)" 2>/dev/null || true; \
		chmod -R u+rwX "$(BUILD_DIR)" 2>/dev/null || true; \
	fi
	rm -rf "$(BUILD_DIR)" dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

version: ## Show current app version
	@echo "$(APP_VERSION)"
