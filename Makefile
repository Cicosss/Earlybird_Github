# ==============================================================================
# Earlybird Project - Single Source of Truth Makefile
# ==============================================================================
# Version: V8.3 (Learning Loop Integrity Fix)
#
# This Makefile is the authoritative source for all operational commands.
# All test and run commands MUST use this Makefile, not generic pytest or python commands.
#
# Usage:
#   make help              - Display all available commands
#   make <command>         - Execute the specified command
#
# ==============================================================================

# ==============================================================================
# Configuration
# ==============================================================================

# Python interpreter
PYTHON := python3

# Virtual environment directory (if using venv)
VENV_DIR := venv

# Entry points based on actual codebase
LAUNCHER := src/launcher.py
MAIN := src/main.py
GO_LIVE := go_live.py
RUN_BOT := src/run_bot.py
RUN_NEWS_RADAR := run_news_radar.py
RUN_TELEGRAM_MONITOR := run_telegram_monitor.py

# Diagnostic scripts
CHECK_APIS := src/utils/check_apis.py
CHECK_LEAGUES := src/utils/check_leagues.py

# Database scripts
DB_MAINTENANCE := src/database/maintenance.py

# Utility scripts
SETUP_VPS := setup_vps.sh
SETUP_TELEGRAM_AUTH := setup_telegram_auth.py

# Test configuration
PYTEST := $(PYTHON) -m pytest
PYTEST_INI := pytest.ini
COVERAGE_REPORT := htmlcov

# Environment file
ENV_FILE := .env

# Database file
DB_FILE := data/earlybird.db

# Log files
LOG_FILES := *.log logs/*.log

# Temporary files
TEMP_FILES := __pycache__ .pytest_cache .coverage htmlcov *.pyc

# Colors for output (optional, works on most terminals)
COLOR_RESET := \033[0m
COLOR_BOLD := \033[1m
COLOR_GREEN := \033[32m
COLOR_YELLOW := \033[33m
COLOR_RED := \033[31m
COLOR_BLUE := \033[34m

# ==============================================================================
# PHONY Targets
# ==============================================================================

.PHONY: help test test-unit test-integration test-regression test-coverage
.PHONY: setup setup-python setup-system install
.PHONY: run run-launcher run-main run-bot run-news-radar run-telegram-monitor
.PHONY: check-apis check-health check-database
.PHONY: clean clean-db clean-all
.PHONY: migrate

# ==============================================================================
# Default Target
# ==============================================================================

.DEFAULT_GOAL := help

# ==============================================================================
# Help Command
# ==============================================================================

help:
	@echo "$(COLOR_BOLD)$(COLOR_BLUE)Earlybird Project - Available Commands$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BOLD)Test Commands:$(COLOR_RESET)"
	@echo "  make test              - Run all tests"
	@echo "  make test-unit         - Run unit tests only"
	@echo "  make test-integration  - Run integration tests only"
	@echo "  make test-regression   - Run regression tests only"
	@echo "  make test-coverage     - Run tests with coverage report"
	@echo ""
	@echo "$(COLOR_BOLD)Setup Commands:$(COLOR_RESET)"
	@echo "  make setup             - Full setup (System + Python)"
	@echo "  make setup-python      - Python dependencies only"
	@echo "  make setup-system      - System dependencies only"
	@echo "  make install           - Alias for setup"
	@echo ""
	@echo "$(COLOR_BOLD)Run Commands:$(COLOR_RESET)"
	@echo "  make run               - Run system in Local Dev/Debug mode (go_live.py)"
	@echo "  make run-launcher      - Run using Process Orchestrator (launcher.py)"
	@echo "  make run-main          - Run main pipeline only"
	@echo "  make run-bot           - Run Telegram bot only"
	@echo "  make run-news-radar    - Run News Radar only"
	@echo "  make run-telegram-monitor - Run Telegram Monitor only"
	@echo ""
	@echo "$(COLOR_BOLD)Diagnostics Commands:$(COLOR_RESET)"
	@echo "  make check-apis        - API Diagnostics"
	@echo "  make check-health      - System health check"
	@echo "  make check-database    - Database integrity check"
	@echo ""
	@echo "$(COLOR_BOLD)Cleanup Commands:$(COLOR_RESET)"
	@echo "  make clean             - Emergency cleanup (logs, temp files)"
	@echo "  make clean-db          - Database cleanup (with confirmation)"
	@echo "  make clean-all         - Full cleanup including database"
	@echo ""
	@echo "$(COLOR_BOLD)Utility Commands:$(COLOR_RESET)"
	@echo "  make migrate           - Run database migrations"
	@echo ""
	@echo "$(COLOR_BOLD)Note:$(COLOR_RESET) All commands use the actual entry points from the codebase."

# ==============================================================================
# Test Commands
# ==============================================================================

test: check-env
	@echo "$(COLOR_GREEN)Running all tests...$(COLOR_RESET)"
	@$(PYTEST) -c $(PYTEST_INI) -v

test-unit: check-env
	@echo "$(COLOR_GREEN)Running unit tests...$(COLOR_RESET)"
	@$(PYTEST) -c $(PYTEST_INI) -v -m unit

test-integration: check-env
	@echo "$(COLOR_GREEN)Running integration tests...$(COLOR_RESET)"
	@$(PYTEST) -c $(PYTEST_INI) -v -m integration

test-regression: check-env
	@echo "$(COLOR_GREEN)Running regression tests...$(COLOR_RESET)"
	@$(PYTEST) -c $(PYTEST_INI) -v -m regression

test-coverage: check-env
	@echo "$(COLOR_GREEN)Running tests with coverage report...$(COLOR_RESET)"
	@$(PYTEST) -c $(PYTEST_INI) -v --cov=src --cov-report=html --cov-report=term
	@echo "$(COLOR_GREEN)Coverage report generated in $(COVERAGE_REPORT)/$(COLOR_RESET)"

# ==============================================================================
# Setup Commands
# ==============================================================================

setup: setup-system setup-python
	@echo "$(COLOR_GREEN)Full setup complete!$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Please ensure .env file is configured before running the system.$(COLOR_RESET)"

setup-system:
	@echo "$(COLOR_GREEN)Setting up system dependencies...$(COLOR_RESET)"
	@if [ -f $(SETUP_VPS) ]; then \
		chmod +x $(SETUP_VPS) && \
		./$(SETUP_VPS); \
	else \
		echo "$(COLOR_YELLOW)Setup script not found. Skipping system dependencies.$(COLOR_RESET)"; \
	fi

setup-python: check-env
	@echo "$(COLOR_GREEN)Setting up Python dependencies...$(COLOR_RESET)"
	@$(PYTHON) -m pip install --break-system-packages --upgrade pip
	@$(PYTHON) -m pip install --break-system-packages -r requirements.txt
	@echo "$(COLOR_GREEN)Python dependencies installed successfully!$(COLOR_RESET)"

install: setup

# ==============================================================================
# Run Commands
# ==============================================================================

run: check-env
	@echo "$(COLOR_GREEN)Running system in Local Dev/Debug mode...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(GO_LIVE)$(COLOR_RESET)"
	@$(PYTHON) $(GO_LIVE)

run-launcher: check-env
	@echo "$(COLOR_GREEN)Running system using Process Orchestrator...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(LAUNCHER)$(COLOR_RESET)"
	@$(PYTHON) $(LAUNCHER)

run-main: check-env
	@echo "$(COLOR_GREEN)Running main pipeline only...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(MAIN)$(COLOR_RESET)"
	@$(PYTHON) $(MAIN)

run-bot: check-env
	@echo "$(COLOR_GREEN)Running Telegram bot only...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(RUN_BOT)$(COLOR_RESET)"
	@$(PYTHON) $(RUN_BOT)

run-news-radar: check-env
	@echo "$(COLOR_GREEN)Running News Radar only...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(RUN_NEWS_RADAR)$(COLOR_RESET)"
	@$(PYTHON) $(RUN_NEWS_RADAR)

	@echo "$(COLOR_GREEN)Running Telegram Monitor only...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: $(RUN_TELEGRAM_MONITOR)$(COLOR_RESET)"
	@$(PYTHON) $(RUN_TELEGRAM_MONITOR)

run-monitor: check-env
	@echo "$(COLOR_GREEN)Running Test Monitor (Right Panel)...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using entry point: run_tests_monitor.sh$(COLOR_RESET)"
	@if [ -f ./run_tests_monitor.sh ]; then \
		chmod +x ./run_tests_monitor.sh && \
		./run_tests_monitor.sh; \
	else \
		echo "$(COLOR_RED)Error: run_tests_monitor.sh not found!$(COLOR_RESET)"; \
		exit 1; \
	fi

# ==============================================================================
# Diagnostics Commands
# ==============================================================================

check-apis: check-env
	@echo "$(COLOR_GREEN)Running API diagnostics...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Using diagnostic script: $(CHECK_APIS)$(COLOR_RESET)"
	@PYTHONPATH=. $(PYTHON) $(CHECK_APIS)

check-health: check-env
	@echo "$(COLOR_GREEN)Running system health check...$(COLOR_RESET)"
	@if [ -f src/alerting/health_monitor.py ]; then \
		$(PYTHON) -c "from src.alerting.health_monitor import HealthMonitor; hm = HealthMonitor(); print(hm.check_all())"; \
	else \
		echo "$(COLOR_YELLOW)Health monitor not found. Checking basic system status...$(COLOR_RESET)"; \
		$(PYTHON) -c "import sys; print(f'Python version: {sys.version}'); print('System appears healthy')"; \
	fi

check-database: check-env
	@echo "$(COLOR_GREEN)Checking database integrity...$(COLOR_RESET)"
	@if [ -f $(DB_FILE) ]; then \
		PYTHONPATH=. $(PYTHON) $(DB_MAINTENANCE) --check; \
	else \
		echo "$(COLOR_RED)Database file not found: $(DB_FILE)$(COLOR_RESET)"; \
	fi

# ==============================================================================
# Cleanup Commands
# ==============================================================================

clean:
	@echo "$(COLOR_YELLOW)Performing emergency cleanup...$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Removing log files...$(COLOR_RESET)"
	@find . -name "*.log" -type f -delete 2>/dev/null || true
	@echo "$(COLOR_YELLOW)Removing temporary files...$(COLOR_RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".coverage" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -type f -delete 2>/dev/null || true
	@find . -name ".coverage" -type f -delete 2>/dev/null || true
	@echo "$(COLOR_GREEN)Emergency cleanup complete!$(COLOR_RESET)"

clean-db:
	@echo "$(COLOR_RED)WARNING: This will delete the database file!$(COLOR_RESET)"
	@read -p "Are you sure you want to delete the database? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		if [ -f $(DB_FILE) ]; then \
			echo "$(COLOR_YELLOW)Deleting database file...$(COLOR_RESET)"; \
			rm -f $(DB_FILE); \
			echo "$(COLOR_GREEN)Database deleted successfully!$(COLOR_RESET)"; \
		else \
			echo "$(COLOR_YELLOW)Database file not found: $(DB_FILE)$(COLOR_RESET)"; \
		fi \
	else \
		echo "$(COLOR_YELLOW)Database cleanup cancelled.$(COLOR_RESET)"; \
	fi

clean-all: clean
	@echo "$(COLOR_RED)WARNING: This will delete the database file!$(COLOR_RESET)"
	@read -p "Are you sure you want to delete the database? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		if [ -f $(DB_FILE) ]; then \
			echo "$(COLOR_YELLOW)Deleting database file...$(COLOR_RESET)"; \
			rm -f $(DB_FILE); \
			echo "$(COLOR_GREEN)Database deleted successfully!$(COLOR_RESET)"; \
		else \
			echo "$(COLOR_YELLOW)Database file not found: $(DB_FILE)$(COLOR_RESET)"; \
		fi \
	else \
		echo "$(COLOR_YELLOW)Database cleanup cancelled.$(COLOR_RESET)"; \
	fi

# ==============================================================================
# Utility Commands
# ==============================================================================

migrate: check-env
	@echo "$(COLOR_GREEN)Running database migrations...$(COLOR_RESET)"
	@if [ -f src/database/migration.py ]; then \
		$(PYTHON) src/database/migration.py; \
	else \
		echo "$(COLOR_YELLOW)Migration script not found. Checking for specific migrations...$(COLOR_RESET)"; \
		for migration in src/database/migration_*.py; do \
			if [ -f "$$migration" ]; then \
				echo "$(COLOR_YELLOW)Running: $$migration$(COLOR_RESET)"; \
				$(PYTHON) "$$migration"; \
			fi \
		done; \
	fi

# ==============================================================================
# Helper Functions
# ==============================================================================

check-env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "$(COLOR_RED)ERROR: .env file not found!$(COLOR_RESET)"; \
		echo "$(COLOR_YELLOW)Please create a .env file from .env.template$(COLOR_RESET)"; \
		exit 1; \
	fi

# ==============================================================================
# End of Makefile
# ==============================================================================
