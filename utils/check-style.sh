#!/bin/bash -e

fail() {
    echo "The code is not formatted according to the current style. You can autoformat your code running:"
    echo "    tox -e py3-format"
    exit 1
}

black --check --diff . \
|| fail

isort --check-only --diff . \
|| fail
