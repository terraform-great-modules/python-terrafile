#!/usr/bin/env python3
import os
import sys

from terrafile import main

if len(sys.argv) > 1:
    path = sys.argv[1]
else:
    path = os.getcwd()

main(path)
