#!/bin/bash
#
# Bootstrap sandbox environment for sqlalchemy-cratedb
#
# - Create a Python virtualenv
# - Install all dependency packages and modules
# - Install package in editable mode
# - Drop user into an activated virtualenv
#
# Synopsis::
#
#     source bootstrap.sh
#


# Trace all invocations.
# set -x

# Default variables.
CRATEDB_VERSION=${CRATEDB_VERSION:-5.5.1}
SQLALCHEMY_VERSION=${SQLALCHEMY_VERSION:-<2.1}


function print_header() {
    printf '=%.0s' {1..42}; echo
    echo "$1"
    printf '=%.0s' {1..42}; echo
}

function ensure_virtualenv() {
    # Create a Python virtualenv with current version of Python 3.
    # TODO: Maybe take `pyenv` into account.
    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
    fi
}

function activate_virtualenv() {
    # Activate Python virtualenv.
    source .venv/bin/activate
}

function before_setup() {

    # When `wheel` is installed, Python will build `wheel` packages from all
    # acquired `sdist` packages and will store them into `~/.cache/pip`, where
    # they will be picked up by the caching machinery and will be reused on
    # subsequent invocations when run on CI. This makes a *significant*
    # difference on total runtime on CI, it is about 2x faster.
    #
    # Otherwise, there will be admonitions like:
    #   Using legacy 'setup.py install' for foobar, since package 'wheel' is
    #   not installed.
    #
    pip install wheel

}

function setup_package() {

    # Upgrade `pip` to support `--pre` option.
    pip install --upgrade pip

    # Conditionally add `--pre` option, to allow installing prerelease packages.
    PIP_OPTIONS="${PIP_OPTIONS:-}"
    if [ "${PIP_ALLOW_PRERELEASE}" == "true" ]; then
      PIP_OPTIONS+=" --pre"
    fi

    # Install package in editable mode.
    pip install ${PIP_OPTIONS} --use-pep517 --prefer-binary --editable='.[all,develop,test]'

    # Install designated SQLAlchemy version.
    if [ -n "${SQLALCHEMY_VERSION}" ]; then
      if [ "${SQLALCHEMY_VERSION}" = "latest" ]; then
        pip install ${PIP_OPTIONS} --upgrade "sqlalchemy"
      else
        pip install ${PIP_OPTIONS} --upgrade "sqlalchemy${SQLALCHEMY_VERSION}"
      fi
    fi

}

function finalize() {

    # Some steps before dropping into the activated virtualenv.
    echo
    echo "Sandbox environment ready"
    echo -n "Using SQLAlchemy version: "
    python -c 'import sqlalchemy; print(sqlalchemy.__version__)'
    echo

}

function main() {
    ensure_virtualenv
    activate_virtualenv
    before_setup
    setup_package
    finalize
}

function lint() {
    poe lint
}

main
