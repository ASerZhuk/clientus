#!/bin/sh
# Run the production build exactly as the server does: the standalone server + its static files. Usage: sh scripts/serve.sh <port>
set -eu
cd "$(dirname "$0")/.."
rm -rf .next/standalone/.next/static .next/standalone/public
cp -a .next/static .next/standalone/.next/static
[ -d public ] && cp -a public .next/standalone/public
PORT=${1:-3000} HOSTNAME=${HOSTNAME:-0.0.0.0} exec node .next/standalone/server.js
