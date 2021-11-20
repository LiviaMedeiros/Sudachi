#!/bin/bash
BASEDIR=$(dirname "${0}")
pip install -r "${BASEDIR}/requirements.txt" -Ut "${BASEDIR}/lib"
exit 0
