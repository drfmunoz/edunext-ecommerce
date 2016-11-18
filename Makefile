NODE_BIN=./node_modules/.bin
DIFF_COVER_BASE_BRANCH=master

help:
	@echo '                                                                                     		'
	@echo 'Makefile for the edX ecommerce project.                                              		'
	@echo '                                                                                     		'
	@echo 'Usage:                                                                               		'
	@echo '    make requirements                 install requirements for local development     		'
	@echo '    make migrate                      apply migrations                               		'
	@echo '    make serve                        start the dev server at localhost:8002         		'
	@echo '    make clean                        delete generated byte code and coverage reports		'
	@echo '    make validate_js                  run JavaScript unit tests and linting          		'
	@echo '    make validate_python              run Python unit tests and quality checks       		'
	@echo '    make fast_validate_python         run Python unit tests (in parallel) and quality checks '
	@echo '    make quality                      run PEP8 and Pylint                            		'
	@echo '    make validate                     Run Python and JavaScript unit tests and linting 		'
	@echo '    make html_coverage                generate and view HTML coverage report         		'
	@echo '    make accept                       run acceptance tests                           		'
	@echo '    make extract_translations         extract strings to be translated               		'
	@echo '    make dummy_translations           generate dummy translations                    		'
	@echo '    make compile_translations         generate translation files                     		'
	@echo '    make fake_translations            install fake translations                      		'
	@echo '    make pull_translations            pull translations from Transifex               		'
	@echo '    make update_translations          install new translations from Transifex        		'
	@echo '    make clean_static                 delete compiled/compressed static assets'
	@echo '    make static                       compile and compress static assets'
	@echo '                                                                                     		'

requirements.js:
	npm install
	$(NODE_BIN)/bower install

requirements: requirements.js
	pip install -qr requirements/local.txt --exists-action w

migrate:
	python manage.py migrate

serve:
	python manage.py runserver 0.0.0.0:8002

clean:
	find . -name '*.pyc' -delete
	coverage erase
	rm -rf coverage htmlcov

clean_static:
	rm -rf assets/* ecommerce/static/build/*

validate_js:
	rm -rf coverage
	$(NODE_BIN)/gulp test
	$(NODE_BIN)/gulp lint
	$(NODE_BIN)/gulp jscs

validate_python: clean
	PATH=$$PATH:$(NODE_BIN) REUSE_DB=1 coverage run --branch --source=ecommerce ./manage.py test ecommerce \
	--settings=ecommerce.settings.test --with-ignore-docstrings --logging-level=DEBUG
	coverage report
	make quality

fast_validate_python: clean
	REUSE_DB=1 DISABLE_ACCEPTANCE_TESTS=True ./manage.py test ecommerce \
	--settings=ecommerce.settings.test --processes=4 --with-ignore-docstrings --logging-level=DEBUG
	make quality

quality:
	pep8 --config=.pep8 ecommerce acceptance_tests
	pylint --rcfile=pylintrc ecommerce acceptance_tests

validate: validate_python validate_js

theme_static:
	python manage.py update_assets --skip-collect

static: theme_static
	$(NODE_BIN)/r.js -o build.js
	python manage.py collectstatic --noinput -v0
	python manage.py compress -v0 --force

html_coverage:
	coverage html && open htmlcov/index.html

diff_coverage: validate fast_diff_coverage

fast_diff_coverage:
	coverage xml
	diff-cover coverage.xml --compare-branch=$(DIFF_COVER_BASE_BRANCH)

accept:
	nosetests --with-ignore-docstrings -v acceptance_tests --with-xunit --xunit-file=acceptance_tests/xunit.xml

extract_translations:
	cd ecommerce && i18n_tool extract -v

dummy_translations:
	cd ecommerce && i18n_tool dummy -v

compile_translations:
	cd ecommerce && i18n_tool generate -v

fake_translations: extract_translations dummy_translations compile_translations

pull_translations:
	cd ecommerce && tx pull -a

push_translations:
	cd ecommerce && tx push -s

update_translations: pull_translations fake_translations

# Targets in a Makefile which do not produce an output file with the same name as the target name
.PHONY: help requirements migrate serve clean validate_python quality validate_js validate html_coverage accept \
	extract_translations dummy_translations compile_translations fake_translations pull_translations \
	push_translations update_translations fast_validate_python clean_static
