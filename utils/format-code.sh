#!/bin/bash -e

black .
isort --profile=black --apply .
